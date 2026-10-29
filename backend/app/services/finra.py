"""FINRA margin statistics: how much investors borrow from brokers to buy stocks.

Monthly, published about three weeks after month end. Amounts are in $ millions.
"""

from __future__ import annotations

import io

import httpx
import pandas as pd

from app.cache import ttl_cache

URL = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"
DEBIT = "Debit Balances in Customers' Securities Margin Accounts"
CASH = "Free Credit Balances in Customers' Cash Accounts"


class FinraUnavailable(RuntimeError):
    pass


def margin_summary(df: pd.DataFrame) -> dict:
    """Latest margin debt in $B with 1-month / 1-year change and its 5-year range."""
    s = pd.Series(pd.to_numeric(df[DEBIT], errors="coerce").values, index=pd.to_datetime(df["Year-Month"], format="%Y-%m")).dropna().sort_index()
    latest = s.iloc[-1]
    five = s[s.index > s.index[-1] - pd.DateOffset(years=5)]
    pct = lambda prev: round((latest / prev - 1) * 100, 1) if prev else None  # noqa: E731
    month_ago = s.get(s.index[-1] - pd.DateOffset(months=1))
    year_ago = s.get(s.index[-1] - pd.DateOffset(years=1))
    return {
        "as_of": s.index[-1].strftime("%Y-%m"),
        "value": round(latest / 1000, 1),
        "change_1m": pct(month_ago),
        "change_1y": pct(year_ago),
        "low_5y": round(five.min() / 1000, 1),
        "high_5y": round(five.max() / 1000, 1),
        "points": [[d.strftime("%Y-%m"), round(v / 1000, 1)] for d, v in s[s.index > s.index[-1] - pd.DateOffset(years=10)].items()],
    }


@ttl_cache(seconds=12 * 60 * 60)
def margin() -> dict:
    try:
        r = httpx.get(URL, headers={"User-Agent": "Mozilla/5.0 (stock-scout personal research)"}, timeout=30)
        r.raise_for_status()
        return margin_summary(pd.read_excel(io.BytesIO(r.content)))
    except Exception as exc:
        raise FinraUnavailable("FINRA 신용거래 통계를 불러오지 못했어요.") from exc
