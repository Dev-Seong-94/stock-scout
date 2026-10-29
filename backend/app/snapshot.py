"""Daily screener snapshot.

Screening thousands of tickers live would mean thousands of slow requests per
click, so once a day we compute every metric for the universe and keep the
result in data/snapshot.parquet. The screener then filters that file
instantly. Nothing about you is stored; it's a cache of public market data.

Run:  python -m scripts.build_snapshot          (from the backend folder)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from app.config import settings
from app.indicators import _clean, cagr, price_indicators

log = logging.getLogger(__name__)

SNAPSHOT = settings.data_dir / "snapshot.parquet"
META = settings.data_dir / "snapshot_meta.json"
PARTIAL = settings.data_dir / "snapshot.partial.parquet"
PARTIAL_META = settings.data_dir / "snapshot.partial.json"


def _pct(value) -> float | None:
    v = _clean(value)
    return None if v is None else v * 100


def fundamentals_from_info(info: dict) -> dict:
    """Map Yahoo's quoteSummary fields to our metric keys and units."""
    price = _clean(info.get("currentPrice") or info.get("regularMarketPrice"))
    market_cap = _clean(info.get("marketCap"))
    fcf = _clean(info.get("freeCashflow"))
    dividend_rate = _clean(info.get("dividendRate"))
    avg_volume = _clean(info.get("averageVolume"))
    debt_to_equity = _clean(info.get("debtToEquity"))
    return {
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": price,
        "pe": _clean(info.get("trailingPE")),
        "forward_pe": _clean(info.get("forwardPE")),
        "peg": _clean(info.get("trailingPegRatio") or info.get("pegRatio")),
        "pb": _clean(info.get("priceToBook")),
        "ps": _clean(info.get("priceToSalesTrailing12Months")),
        "ev_ebitda": _clean(info.get("enterpriseToEbitda")),
        "fcf_yield": (fcf / market_cap * 100) if fcf is not None and market_cap else None,
        "dividend_yield": (dividend_rate / price * 100) if dividend_rate and price else 0.0 if price else None,
        "roe": _pct(info.get("returnOnEquity")),
        "roa": _pct(info.get("returnOnAssets")),
        "gross_margin": _pct(info.get("grossMargins")),
        "operating_margin": _pct(info.get("operatingMargins")),
        "net_margin": _pct(info.get("profitMargins")),
        "revenue_growth": _pct(info.get("revenueGrowth")),
        "earnings_growth": _pct(info.get("earningsGrowth")),
        # Yahoo reports D/E as a percentage (150 = 1.5x).
        "debt_to_equity": debt_to_equity / 100 if debt_to_equity is not None else None,
        "current_ratio": _clean(info.get("currentRatio")),
        "beta": _clean(info.get("beta")),
        "market_cap": market_cap / 1e9 if market_cap else None,
        "avg_dollar_volume": avg_volume * price / 1e6 if avg_volume and price else None,
        "short_float": _pct(info.get("shortPercentOfFloat")),
        "insider_pct": _pct(info.get("heldPercentInsiders")),
        "institution_pct": _pct(info.get("heldPercentInstitutions")),
    }


def _row(df: pd.DataFrame, *names: str) -> pd.Series | None:
    for name in names:
        if name in df.index:
            return df.loc[name].dropna()
    return None


def financial_extras(income: pd.DataFrame) -> dict:
    """Metrics that need multi-year statements: 3y revenue CAGR, interest coverage."""
    out = {"revenue_cagr_3y": None, "interest_coverage": None}
    if income is None or income.empty:
        return out
    income = income.reindex(sorted(income.columns, reverse=True), axis=1)  # newest first
    revenue = _row(income, "Total Revenue", "Operating Revenue")
    if revenue is not None and len(revenue) >= 4:
        out["revenue_cagr_3y"] = cagr(revenue.iloc[3], revenue.iloc[0], 3)
    ebit = _row(income, "EBIT", "Operating Income")
    interest = _row(income, "Interest Expense", "Interest Expense Non Operating")
    if ebit is not None and interest is not None and len(ebit) and len(interest):
        expense = abs(float(interest.iloc[0]))
        if expense > 0:
            out["interest_coverage"] = _clean(float(ebit.iloc[0]) / expense)
    return out


def build_row(symbol: str, history: pd.DataFrame, info: dict, income: pd.DataFrame | None) -> dict:
    row = {"symbol": symbol}
    row |= fundamentals_from_info(info)
    row |= price_indicators(history) if history is not None and not history.empty else {}
    row |= financial_extras(income if income is not None else pd.DataFrame())
    if row.get("price") is None and history is not None and not history.empty:
        row["price"] = _clean(history["Close"].dropna().iloc[-1])
    return row


# ---------------------------------------------------------------------------
# Building (network)
# ---------------------------------------------------------------------------

status = {"running": False, "done": 0, "total": 0, "started_at": None, "error": None}
_lock = threading.Lock()


def _download_histories(symbols: list[str], chunk: int = 100) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i : i + chunk]
        try:
            # threads=False: parallel downloads open many sockets at once and get rate limited.
            df = yf.download(part, period="2y", auto_adjust=True, progress=False, group_by="ticker", threads=False)
        except Exception as exc:
            log.warning("bulk price download failed for %s…: %s", part[0], exc)
            continue
        if df is None or df.empty:
            continue
        for sym in part:
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    level = 0 if sym in df.columns.get_level_values(0) else 1
                    sub = df.xs(sym, axis=1, level=level)
                else:
                    sub = df
                sub = sub.dropna(how="all")
                if "Close" in sub and sub["Close"].notna().sum() > 0:
                    sub.index = pd.to_datetime(sub.index).tz_localize(None)
                    out[sym] = sub
            except KeyError:
                continue
        time.sleep(1)
    return out


def _single_history(ticker) -> pd.DataFrame:
    """Fallback when a ticker was missing from the bulk download."""
    df = ticker.history(period="2y", auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def _with_retry(fn: Callable, *args, attempts: int = 3):
    for attempt in range(attempts):
        try:
            return fn(*args)
        except Exception as exc:  # rate limits show up as various exceptions
            wait = 2 ** attempt * 3
            log.info("retry %s%s in %ss: %s", fn.__name__, args, wait, exc)
            time.sleep(wait)
    return None


def _raise_open_file_limit(target: int = 8192) -> None:
    """macOS allows only 256 open files per process by default. yfinance opens
    sockets and cache files for every ticker, so a 500-ticker run can hit
    "[Errno 24] Too many open files". Raise the soft limit for this process."""
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        wanted = min(target, hard) if hard != resource.RLIM_INFINITY else target
        if soft < wanted:
            resource.setrlimit(resource.RLIMIT_NOFILE, (wanted, hard))
    except (ImportError, ValueError, OSError) as exc:  # Windows has no resource module
        log.info("could not raise open file limit: %s", exc)


def _save_partial(rows: list[dict], failed: list[str]) -> None:
    pd.DataFrame(rows).to_parquet(PARTIAL, index=False)
    PARTIAL_META.write_text(json.dumps({"failed": failed}))


def _load_partial(max_age_hours: float = 20) -> tuple[list[dict], list[str]]:
    """Rows saved by an interrupted run today, so it can continue where it stopped."""
    if not PARTIAL.exists() or time.time() - PARTIAL.stat().st_mtime > max_age_hours * 3600:
        return [], []
    try:
        rows = pd.read_parquet(PARTIAL).to_dict(orient="records")
        failed = json.loads(PARTIAL_META.read_text()).get("failed", []) if PARTIAL_META.exists() else []
        return rows, failed
    except Exception:
        return [], []


def build_snapshot(
    symbols: list[str],
    include_statements: bool = True,
    pause: float = 0.3,
    progress: Callable[[int, int, str], None] | None = None,
    checkpoint_every: int = 25,
    resume: bool = True,
) -> pd.DataFrame:
    _raise_open_file_limit()
    import pyarrow.parquet  # noqa: F401  load the writer up front, not after hundreds of requests
    import yfinance as yf

    rows, failed = _load_partial() if resume else ([], [])
    done = {r["symbol"] for r in rows} | set(failed)
    if done:
        log.info("resuming: %d tickers already done", len(done))
    todo = [s for s in symbols if s not in done]

    histories = _download_histories(todo) if todo else {}
    log.info("bulk prices: %d of %d tickers", len(histories), len(todo))
    no_prices: list[str] = []
    for n, sym in enumerate(todo, start=1):
        t = yf.Ticker(sym)
        info = _with_retry(lambda s=t: s.info or {}) or {}
        income = _with_retry(lambda s=t: s.income_stmt) if include_statements else None
        hist = histories.get(sym)
        if hist is None:
            hist = _with_retry(lambda s=t: _single_history(s))
            if hist is None or hist.empty:
                no_prices.append(sym)
                hist = pd.DataFrame()
        if not info and hist.empty:
            failed.append(sym)
        else:
            rows.append(build_row(sym, hist, info, income))
        del t
        if progress:
            progress(len(done) + n, len(symbols), sym)
        if n % checkpoint_every == 0:
            _save_partial(rows, failed)
        time.sleep(pause)

    df = pd.DataFrame(rows)
    df.to_parquet(SNAPSHOT, index=False)
    META.write_text(
        json.dumps(
            {
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "count": len(df),
                "failed": failed,
                "no_prices": no_prices,
                "statements": include_statements,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    PARTIAL.unlink(missing_ok=True)
    PARTIAL_META.unlink(missing_ok=True)
    return df


def start_background_build(symbols: list[str]) -> bool:
    """Kick off a rebuild without blocking the API. False if one is running."""
    with _lock:
        if status["running"]:
            return False
        status.update(running=True, done=0, total=len(symbols), error=None,
                      started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def progress(done: int, total: int, _sym: str) -> None:
        status.update(done=done, total=total)

    def run() -> None:
        try:
            build_snapshot(symbols, progress=progress)
            from app import screener

            screener.reload()
        except Exception as exc:
            log.exception("snapshot build failed")
            status["error"] = str(exc)
        finally:
            status["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return True


def load_meta() -> dict | None:
    return json.loads(META.read_text()) if META.exists() else None
