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

from app.cheapness import NO_FCF_SECTORS, cash_value_gap, pe_vs_own
from app.config import settings
from app.indicators import _clean, cagr, price_indicators
from app.valuation import valuation_ranges

log = logging.getLogger(__name__)

PRICE_METRIC_DAYS = 731
HISTORY_PERIOD = "5y"  # own-past PER needs years of prices; price metrics use only the last two

SNAPSHOT = settings.data_dir / "snapshot.parquet"
META = settings.data_dir / "snapshot_meta.json"
PARTIAL = settings.data_dir / "snapshot.partial.parquet"
PARTIAL_META = settings.data_dir / "snapshot.partial.json"


def _pct(value) -> float | None:
    v = _clean(value)
    return None if v is None else v * 100



def fcf_from_statement(cashflow: pd.DataFrame | None) -> float | None:
    """Free cash flow (operating cash flow − capex) from the TTM cash flow statement.

    Yahoo's info["freeCashflow"] is a levered estimate that can be far off
    (NVDA: $42B vs $127B reported), so the statement comes first."""
    if cashflow is None or cashflow.empty:
        return None
    cashflow = cashflow.reindex(sorted(cashflow.columns, reverse=True), axis=1)  # newest first
    fcf = _row(cashflow, "Free Cash Flow")
    if fcf is not None and len(fcf):
        return _clean(float(fcf.iloc[0]))
    ocf = _row(cashflow, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex = _row(cashflow, "Capital Expenditure")
    if ocf is not None and len(ocf):
        return _clean(float(ocf.iloc[0]) + (float(capex.iloc[0]) if capex is not None and len(capex) else 0.0))
    return None


def fundamentals_from_info(info: dict, fcf: float | None = None) -> dict:
    """Map Yahoo's quoteSummary fields to our metric keys and units.

    `fcf` is the statement-based free cash flow; without it (fast builds, missing
    statements) Yahoo's own estimate is used."""
    price = _clean(info.get("currentPrice") or info.get("regularMarketPrice"))
    market_cap = _clean(info.get("marketCap"))
    if fcf is None:
        fcf = _clean(info.get("freeCashflow"))
    operating_cf = _clean(info.get("operatingCashflow"))
    if info.get("sector") in NO_FCF_SECTORS:
        fcf = operating_cf = None
    dividend_rate = _clean(info.get("dividendRate"))
    avg_volume = _clean(info.get("averageVolume"))
    debt_to_equity = _clean(info.get("debtToEquity"))
    net_margin = _pct(info.get("profitMargins"))
    net_income, revenue = _clean(info.get("netIncomeToCommon")), _clean(info.get("totalRevenue"))
    if net_margin == 0 and net_income and revenue:
        # Yahoo reports deeply negative margins as 0; recompute them.
        net_margin = net_income / revenue * 100
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
        "net_margin": net_margin,
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
        "cash_runway": cash_runway_months(
            _clean(info.get("totalCash")), fcf, operating_cf
        ),
    }


def cash_runway_months(cash: float | None, fcf: float | None, operating_cf: float | None) -> float | None:
    """Months of cash at the current burn. None when the company is not burning
    cash. Uses whichever of FCF / operating cash flow burns more (conservative)."""
    flows = [f for f in (fcf, operating_cf) if f is not None]
    if cash is None or not flows or min(flows) >= 0:
        return None
    return cash / -min(flows) * 12


def _row(df: pd.DataFrame, *names: str) -> pd.Series | None:
    for name in names:
        if name in df.index:
            return df.loc[name].dropna()
    return None


def financial_extras(income: pd.DataFrame) -> dict:
    """Metrics that need multi-year statements: 3y revenue CAGR, interest
    coverage, share count change and gross margin change (newest vs prior year)."""
    out = {"revenue_cagr_3y": None, "interest_coverage": None, "share_change_1y": None, "gross_margin_change": None}
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
    shares = _row(income, "Diluted Average Shares", "Basic Average Shares")
    if shares is not None and len(shares) >= 2 and shares.iloc[1] > 0:
        out["share_change_1y"] = _clean((shares.iloc[0] / shares.iloc[1] - 1) * 100)
    gross = _row(income, "Gross Profit")
    if gross is not None and revenue is not None and len(gross) >= 2 and len(revenue) >= 2:
        both = pd.concat([gross, revenue], axis=1, keys=["g", "r"]).dropna()
        both = both[both["r"] > 0].sort_index(ascending=False)
        if len(both) >= 2:
            margins = both["g"] / both["r"] * 100
            out["gross_margin_change"] = _clean(margins.iloc[0] - margins.iloc[1])
    return out


def recent_prices(history: pd.DataFrame) -> pd.DataFrame:
    """The last two years: price metrics stay the same however much history was loaded."""
    return history[history.index >= history.index.max() - pd.Timedelta(days=PRICE_METRIC_DAYS)]


def own_past_pe(history: pd.DataFrame | None, income: pd.DataFrame | None) -> dict:
    """Last fiscal year's PER and its median over the available history (annual figures, weekly prices)."""
    empty = {"pe_own_current": None, "pe_own_median": None, "pe_own_since": None}
    if history is None or history.empty or income is None or income.empty:
        return empty
    close = history["Close"].dropna()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    pe = valuation_ranges(close.resample("W-FRI").last().dropna(), income)["pe"]
    if pe is None:
        return empty
    return {"pe_own_current": pe["current"], "pe_own_median": pe["median"], "pe_own_since": pe["since"]}


def build_row(
    symbol: str,
    history: pd.DataFrame,
    info: dict,
    income: pd.DataFrame | None,
    cashflow: pd.DataFrame | None = None,
) -> dict:
    row = {"symbol": symbol}
    row |= fundamentals_from_info(info, fcf_from_statement(cashflow))
    row |= price_indicators(recent_prices(history)) if history is not None and not history.empty else {}
    row |= financial_extras(income if income is not None else pd.DataFrame())
    row |= own_past_pe(history, income)
    row["pe_vs_own"] = pe_vs_own(row["pe_own_current"], row["pe_own_median"])
    row["cash_value_gap"] = cash_value_gap(row.get("fcf_yield"))
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
            df = yf.download(part, period=HISTORY_PERIOD, auto_adjust=True, progress=False, group_by="ticker", threads=False)
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
    df = ticker.history(period=HISTORY_PERIOD, auto_adjust=True)
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
        cashflow = _with_retry(lambda s=t: s.ttm_cashflow) if include_statements else None
        hist = histories.get(sym)
        if hist is None:
            hist = _with_retry(lambda s=t: _single_history(s))
            if hist is None or hist.empty:
                no_prices.append(sym)
                hist = pd.DataFrame()
        if not info and hist.empty:
            failed.append(sym)
        else:
            rows.append(build_row(sym, hist, info, income, cashflow))
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
