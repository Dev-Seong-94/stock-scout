"""Market-wide insider buying vs selling, from SEC Form 4 filings.

Only open-market buys (code P) and sells (code S) count. Awards, tax
withholding and gifts are not trading decisions and are left out.

- Recent weeks: the EDGAR daily index lists every Form 4; the ones whose issuer
  is in the screener universe are fetched and parsed (≈ 300 a day, kept on disk
  per day in data/insiders/days/ since filed documents never change).
- "Usual" level: SEC's quarterly Insider Transactions Data Sets, last 4
  published quarters (they lag by a few months), summarised once a month.
"""

from __future__ import annotations

import io
import json
import logging
import re
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import httpx
import pandas as pd

from app import filing_summary as fs
from app.config import settings
from app.services import sec

log = logging.getLogger(__name__)

DIR = settings.data_dir / "insiders"
DAYS = DIR / "days"
BASELINE = DIR / "baseline.json"
RECENT_DAYS = 42  # calendar days kept up to date (6 weeks)
BASELINE_QUARTERS = 4
BASELINE_MAX_AGE = timedelta(days=30)
REFRESH_EVERY = 6 * 60 * 60
DATASETS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"
_INTERVAL = 0.15  # the SEC asks for at most 10 requests per second; leave room for the stock pages

status: dict = {"running": False, "done": 0, "total": 0, "error": None, "updated": 0.0}
_lock = threading.Lock()
_last_call = 0.0


# ── pure parts (tested) ──────────────────────────────────────────────────────


def week_start(d: pd.Series) -> pd.Series:
    d = pd.to_datetime(d)
    return (d - pd.to_timedelta(d.dt.day_of_week, unit="D")).dt.normalize()


def weekly(tx: pd.DataFrame) -> pd.DataFrame:
    """tx columns: accession, filed, ticker, code, shares, price.
    One row per week (Monday): filings with an open-market buy / sell and their dollar value."""
    cols = ["week", "buy_filings", "sell_filings", "buy_value", "sell_value"]
    tx = tx[tx["code"].isin(["P", "S"])]
    if tx.empty:
        return pd.DataFrame(columns=cols)
    tx = tx.assign(week=week_start(tx["filed"]), value=tx["shares"] * tx["price"])
    out = []
    for wk, g in tx.groupby("week"):
        buys, sells = g[g["code"] == "P"], g[g["code"] == "S"]
        out.append(
            {
                "week": wk,
                "buy_filings": int(buys["accession"].nunique()),
                "sell_filings": int(sells["accession"].nunique()),
                "buy_value": float(buys["value"].sum()),
                "sell_value": float(sells["value"].sum()),
            }
        )
    return pd.DataFrame(out, columns=cols).sort_values("week").reset_index(drop=True)


def ratio(sells: float, buys: float) -> float | None:
    return round(sells / buys, 1) if buys else None


def top_names(tx: pd.DataFrame, code: str, n: int = 8) -> list[dict]:
    g = tx[tx["code"] == code].assign(value=lambda d: d["shares"] * d["price"])
    if g.empty:
        return []
    agg = g.groupby("ticker").agg(value=("value", "sum"), filings=("accession", "nunique")).sort_values("value", ascending=False)
    return [{"ticker": t, "value": round(float(r.value)), "filings": int(r.filings)} for t, r in agg.head(n).iterrows() if r.value > 0]


# ── data collection ─────────────────────────────────────────────────────────


_rate = threading.Lock()
WORKERS = 6  # requests overlap (each takes ~0.5 s); _get still spaces their starts


def _get(url: str, **kw) -> httpx.Response:
    global _last_call
    with _rate:
        wait = _last_call + _INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
    return httpx.get(url, headers=sec._headers(), timeout=60, **kw)


def _universe_ciks() -> dict[int, str]:
    """CIK → our ticker, for every company in the screener snapshot."""
    from app import screener  # late import: screener loads the snapshot

    df = screener.frame()
    if df is None:
        return {}
    by_ticker = sec.ticker_to_cik()
    out = {}
    for sym in df["symbol"]:
        cik = by_ticker.get(sym.replace("-", ".")) or by_ticker.get(sym)
        if cik:
            out[cik] = sym
    return out


_IDX_LINE = re.compile(r"^(\S+)\s+.+?\s{2,}(\d+)\s+(\d{8})\s+(\S+\.txt)\s*$")


def _form4_paths(day: date, ciks: set[int]) -> list[str] | None:
    """Form 4 submissions filed that day for issuers in ciks; None if the index isn't out yet."""
    url = f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{(day.month - 1) // 3 + 1}/form.{day:%Y%m%d}.idx"
    r = _get(url)
    if r.status_code in (403, 404):
        return None
    r.raise_for_status()
    paths = set()
    for line in r.text.splitlines():
        m = _IDX_LINE.match(line)
        # Each filing is listed under the issuer and under the insider; keep it via the issuer.
        if m and m.group(1) == "4" and int(m.group(2)) in ciks:
            paths.add(m.group(4))
    return sorted(paths)


def _collect_day(day: date, cik_to_ticker: dict[int, str]) -> list[dict] | None:
    paths = _form4_paths(day, set(cik_to_ticker))
    if paths is None:
        return None
    status["total"] += len(paths)

    def fetch(path: str) -> str | None:
        try:
            return _get(f"https://www.sec.gov/Archives/{path}").text
        except httpx.HTTPError as exc:
            log.warning("Form 4 %s failed: %s", path, exc)
            return None
        finally:
            status["done"] += 1

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        texts = list(pool.map(fetch, paths))
    rows = []
    for path, text in zip(paths, texts):
        if text is None:
            continue
        cik = int(path.split("/")[2])  # the issuer's folder: paths were picked by issuer CIK
        m = re.search(r"<XML>\s*(.*?)\s*</XML>", text, re.S)
        parsed = fs.parse_form4(m.group(1)) if m else None
        if not parsed:
            continue
        for code, shares, price in parsed["txs"]:
            if code in ("P", "S"):
                rows.append(
                    {
                        "accession": path.rsplit("/", 1)[1].removesuffix(".txt"),
                        "filed": day.isoformat(),
                        "ticker": cik_to_ticker.get(cik, parsed["ticker"]),
                        "owner": parsed["owner"],
                        "role": parsed["role"],
                        "code": code,
                        "shares": shares,
                        "price": price,
                    }
                )
    return rows


def _update_days(cik_to_ticker: dict[int, str]) -> None:
    DAYS.mkdir(parents=True, exist_ok=True)
    today = date.today()
    for back in range(RECENT_DAYS, 0, -1):
        day = today - timedelta(days=back)
        path = DAYS / f"{day:%Y%m%d}.json"
        if day.weekday() >= 5 or path.exists():
            continue
        rows = _collect_day(day, cik_to_ticker)
        if rows is None:
            if back > 3:  # a holiday: no index will ever come
                path.write_text("[]")
            continue
        path.write_text(json.dumps(rows))


def _dataset_urls() -> list[str]:
    r = _get(DATASETS_PAGE, follow_redirects=True)
    r.raise_for_status()
    links = sorted(set(re.findall(r'href="([^"]+_form345\.zip)"', r.text)))
    return ["https://www.sec.gov" + u if u.startswith("/") else u for u in links[-BASELINE_QUARTERS:]]


def _dataset_tx(url: str, cik_to_ticker: dict[int, str]) -> pd.DataFrame:
    r = _get(url)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    read = lambda name, cols: pd.read_csv(z.open(name), sep="\t", usecols=cols, dtype=str, quoting=3)  # noqa: E731
    sub = read("SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK"])
    sub = sub[sub["DOCUMENT_TYPE"] == "4"]
    sub = sub.assign(cik=pd.to_numeric(sub["ISSUERCIK"], errors="coerce"))
    sub = sub[sub["cik"].isin(cik_to_ticker)]
    trans = read("NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE"])
    tx = trans.merge(sub, on="ACCESSION_NUMBER")
    return pd.DataFrame(
        {
            "accession": tx["ACCESSION_NUMBER"],
            "filed": pd.to_datetime(tx["FILING_DATE"], format="%d-%b-%Y", errors="coerce"),
            "ticker": tx["cik"].map(cik_to_ticker),
            "code": tx["TRANS_CODE"],
            "shares": pd.to_numeric(tx["TRANS_SHARES"], errors="coerce").fillna(0),
            "price": pd.to_numeric(tx["TRANS_PRICEPERSHARE"], errors="coerce").fillna(0),
        }
    ).dropna(subset=["filed"])


def _update_baseline(cik_to_ticker: dict[int, str]) -> None:
    if BASELINE.exists() and datetime.now().timestamp() - BASELINE.stat().st_mtime < BASELINE_MAX_AGE.total_seconds():
        return
    frames = [_dataset_tx(u, cik_to_ticker) for u in _dataset_urls()]
    w = weekly(pd.concat(frames, ignore_index=True))
    w = w.iloc[1:-1]  # first and last weeks are cut off by the quarter boundaries
    BASELINE.write_text(
        json.dumps(
            {
                "since": w["week"].min().strftime("%Y-%m-%d"),
                "until": (w["week"].max() + timedelta(days=6)).strftime("%Y-%m-%d"),
                "weeks": int(len(w)),
                "buy_filings": round(float(w["buy_filings"].mean()), 1),
                "sell_filings": round(float(w["sell_filings"].mean()), 1),
                "buy_value": round(float(w["buy_value"].mean())),
                "sell_value": round(float(w["sell_value"].mean())),
            }
        )
    )


def update() -> None:
    """Fill in missing days and the baseline. Safe to call repeatedly; one run at a time."""
    if not settings.sec_user_agent or not _lock.acquire(blocking=False):
        return
    status.update(running=True, done=0, total=0, error=None)
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        cik_to_ticker = _universe_ciks()
        if cik_to_ticker:
            _update_baseline(cik_to_ticker)
            _update_days(cik_to_ticker)
    except Exception as exc:  # keep what was collected; try again next time
        log.warning("insider update failed: %s", exc)
        status["error"] = "SEC 데이터를 다 받지 못했어요. 잠시 뒤 다시 시도해요."
    finally:
        status.update(running=False, updated=time.time())
        _lock.release()


def refresh_in_background() -> None:
    if not status["running"] and time.time() - status["updated"] > REFRESH_EVERY:
        threading.Thread(target=update, daemon=True).start()


def recent_tx() -> pd.DataFrame:
    rows = []
    for path in sorted(DAYS.glob("*.json")) if DAYS.exists() else []:
        rows += json.loads(path.read_text())
    cols = ["accession", "filed", "ticker", "owner", "role", "code", "shares", "price"]
    return pd.DataFrame(rows, columns=cols)


def baseline() -> dict | None:
    return json.loads(BASELINE.read_text()) if BASELINE.exists() else None
