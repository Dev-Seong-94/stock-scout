"""A stock's valuation against its own past. Pure pandas, no network.

Historical PER/PSR need historical earnings and sales. Yahoo gives about four
fiscal years of annual statements, so each week's price is divided by the
latest annual figure that had been published by then (fiscal year end plus a
reporting lag). Because it uses annual numbers, the current value can differ a
little from the trailing-12-month PER on the metric cards.
"""

from __future__ import annotations

import pandas as pd

from app.indicators import _clean, percentile_rank

REPORT_LAG = pd.Timedelta(days=75)  # 10-K filings land within ~60–90 days
MIN_POINTS = 26  # at least half a year of weekly values


def _annual_row(income: pd.DataFrame, *names: str) -> pd.Series | None:
    for name in names:
        if name in income.index:
            s = pd.to_numeric(income.loc[name], errors="coerce").dropna()
            if not s.empty:
                s.index = pd.to_datetime(s.index)
                return s.sort_index()
    return None


def _as_published(annual: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """For each date, the latest annual value already published by then."""
    available = annual.copy()
    available.index = available.index + REPORT_LAG
    return available.reindex(available.index.union(dates)).ffill().reindex(dates)


def _summary(series: pd.Series) -> dict | None:
    s = series.dropna()
    if len(s) < MIN_POINTS:
        return None
    # None when the latest year is a loss, rather than an old, stale value.
    current = _clean(series.iloc[-1])
    return {
        "current": current,
        "low": _clean(s.min()),
        "high": _clean(s.max()),
        "median": _clean(s.median()),
        "percentile": percentile_rank(s, current) if current is not None else None,
        "since": s.index[0].strftime("%Y-%m-%d"),
        "years": round((s.index[-1] - s.index[0]).days / 365.25, 1),
    }


def valuation_ranges(close: pd.Series, income: pd.DataFrame) -> dict[str, dict | None]:
    """PER and PSR over the available history: current, low, high, median, percentile."""
    out: dict[str, dict | None] = {"pe": None, "ps": None}
    close = close.dropna()
    if close.empty or income is None or income.empty:
        return out
    dates = pd.DatetimeIndex(close.index)

    eps = _annual_row(income, "Diluted EPS", "Basic EPS")
    if eps is not None:
        e = _as_published(eps, dates)
        out["pe"] = _summary((close / e).where(e > 0))  # no PER while losing money

    revenue = _annual_row(income, "Total Revenue", "Operating Revenue")
    shares = _annual_row(income, "Diluted Average Shares", "Basic Average Shares")
    if revenue is not None and shares is not None:
        per_share = _as_published(revenue, dates) / _as_published(shares, dates)
        out["ps"] = _summary((close / per_share).where(per_share > 0))
    return out
