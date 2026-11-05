"""Facts for "왜 떨어졌나?": how a stock fell next to its sector and the market,
and whether recent results got worse. Pure functions.

They compare numbers and never name a cause: no "the market did it", no "the
company is fine". The reader decides.
"""

from __future__ import annotations

import pandas as pd

from app.indicators import _clean, period_return

WINDOWS = {"1m": 21, "3m": 63, "6m": 126, "1y": 251}
WINDOW_LABELS = {"1m": "1개월", "3m": "3개월", "6m": "6개월", "1y": "1년"}
# Which window a sentence talks about: the three-month view unless the stock didn't fall then.
SENTENCE_ORDER = ("3m", "6m", "1y", "1m")

SIMILAR_POINTS = 2.0  # closer than this reads as "about the same"
REVENUE_DROP_PCT = 1.0  # smaller moves would read as "fell 0%"
MARGIN_DROP_POINTS = 2.0
SHARES_RISE_PCT = 5.0
YEAR_AGO_DAYS = (320, 410)


def returns(close: pd.Series | None) -> dict[str, float | None]:
    if close is None:
        return dict.fromkeys(WINDOWS)
    return {name: period_return(close, days) for name, days in WINDOWS.items()}


def _versus(name: str, stock: float, other: float | None) -> str | None:
    if other is None:
        return None
    gap = stock - other
    if abs(gap) < SIMILAR_POINTS:
        return f"{name} 수익률과 비슷해요"
    if other >= 0:
        return f"같은 기간 {name} 수익률은 {other:+.1f}%예요"
    if gap < 0:
        return f"{name}보다 {-gap:.0f}%p 더 떨어졌어요"
    return f"{name}보다 {gap:.0f}%p 덜 떨어졌어요"


def return_facts(stock: dict, sector: dict, market: dict, sector_name: str | None = "섹터") -> list[str]:
    """Fixed sentences comparing the stock's fall with its sector and the S&P 500."""
    if all(v is None for v in stock.values()):
        return []
    window = next((w for w in SENTENCE_ORDER if stock.get(w) is not None and stock[w] < 0), None)
    if window is None:
        return ["이 기간에는 떨어지지 않았어요."]
    fall = stock[window]
    parts = [_versus(sector_name or "섹터", fall, sector.get(window)), _versus("S&P 500", fall, market.get(window))]
    lines = [f"{WINDOW_LABELS[window]} 동안 {-fall:.0f}% 떨어졌어요."]
    lines += [p + "." for p in parts if p]
    return lines


def _value(income: pd.DataFrame, column, *names: str) -> float | None:
    for name in names:
        if name in income.index:
            value = _clean(pd.to_numeric(income.loc[name, column], errors="coerce"))
            if value is not None:
                return value
    return None


def _pct_change(now: float | None, before: float | None) -> float | None:
    if now is None or before is None or before <= 0:
        return None
    return (now / before - 1) * 100


def quarterly_trend(income: pd.DataFrame | None) -> dict | None:
    """The latest quarter against the same quarter a year earlier."""
    if income is None or income.empty:
        return None
    columns = sorted(pd.to_datetime(income.columns), reverse=True)
    latest = columns[0]
    year_ago = next((c for c in columns[1:] if YEAR_AGO_DAYS[0] <= (latest - c).days <= YEAR_AGO_DAYS[1]), None)
    table = income.copy()
    table.columns = pd.to_datetime(table.columns)

    def margin(column) -> float | None:
        revenue = _value(table, column, "Total Revenue", "Operating Revenue")
        operating = _value(table, column, "Operating Income", "EBIT")
        return operating / revenue * 100 if operating is not None and revenue else None

    def line(column, *names: str) -> float | None:
        return _value(table, column, *names) if column is not None else None

    revenue_names = ("Total Revenue", "Operating Revenue")
    share_names = ("Diluted Average Shares", "Basic Average Shares")
    return {
        "quarter": latest.strftime("%Y-%m-%d"),
        "has_year_ago": year_ago is not None,
        "revenue_change": _pct_change(line(latest, *revenue_names), line(year_ago, *revenue_names)),
        "operating_margin": margin(latest),
        "operating_margin_year_ago": margin(year_ago) if year_ago is not None else None,
        "shares_change": _pct_change(line(latest, *share_names), line(year_ago, *share_names)),
    }


def earnings_facts(trend: dict | None) -> list[str]:
    """Sentences only for what got clearly worse. Silence is not a clean bill of health."""
    if not trend:
        return []
    lines = []
    revenue = trend.get("revenue_change")
    if revenue is not None and revenue <= -REVENUE_DROP_PCT:
        lines.append(f"매출이 전년 같은 분기보다 {-revenue:.0f}% 줄었어요.")
    now, before = trend.get("operating_margin"), trend.get("operating_margin_year_ago")
    if now is not None and before is not None and before - now >= MARGIN_DROP_POINTS:
        lines.append(f"영업이익률이 전년 같은 분기보다 {before - now:.0f}%p 낮아졌어요.")
    shares = trend.get("shares_change")
    if shares is not None and shares >= SHARES_RISE_PCT:
        lines.append(f"희석 주식 수가 전년 같은 분기보다 {shares:.0f}% 늘었어요.")
    return lines
