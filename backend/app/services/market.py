"""Prices and company data from Yahoo Finance via yfinance.

yfinance is an unofficial client: fine for personal research, but the data can
be delayed or briefly unavailable, and it is not licensed for redistribution.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import httpx
import pandas as pd
import yfinance as yf

from app.cache import ttl_cache
from app.indicators import _clean

log = logging.getLogger(__name__)

# Market-wide instruments shown on the dashboard.
MARKET_SYMBOLS = {
    "^GSPC": "S&P 500",
    "^IXIC": "나스닥 종합",
    "^VIX": "VIX",
    "DX-Y.NYB": "달러 인덱스",
    "CL=F": "WTI 유가",
    "GC=F": "금",
}

# SPDR sector ETFs → Yahoo sector names used by the screener.
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLF": "Financial Services",
    "XLY": "Consumer Cyclical",
    "XLC": "Communication Services",
    "XLI": "Industrials",
    "XLP": "Consumer Defensive",
    "XLE": "Energy",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Basic Materials",
}


@ttl_cache(seconds=15 * 60)
def history(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


@ttl_cache(seconds=15 * 60)
def closes(symbols: tuple[str, ...], period: str = "1y") -> pd.DataFrame:
    """Close prices for several symbols in one request (columns = symbols)."""
    df = yf.download(
        list(symbols), period=period, auto_adjust=True, progress=False, group_by="column", threads=True
    )
    if df.empty:
        return df
    close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]]
    if not isinstance(df.columns, pd.MultiIndex):
        close.columns = list(symbols)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


@ttl_cache(seconds=60 * 60)
def info(symbol: str) -> dict:
    try:
        return yf.Ticker(symbol).info or {}
    except Exception as exc:  # yfinance raises many things; treat all as "no data"
        log.warning("info(%s) failed: %s", symbol, exc)
        return {}


def quotes(symbols: list[str]) -> list[dict]:
    """Last price and daily change for a short list (watchlist)."""
    if not symbols:
        return []
    df = closes(tuple(sorted(set(symbols))), period="1mo")
    out = []
    for sym in symbols:
        if df.empty or sym not in df:
            out.append({"symbol": sym, "price": None, "change_pct": None})
            continue
        s = df[sym].dropna()
        price = _clean(s.iloc[-1]) if len(s) else None
        prev = _clean(s.iloc[-2]) if len(s) > 1 else None
        change = (price / prev - 1) * 100 if price and prev else None
        out.append({"symbol": sym, "price": price, "change_pct": _clean(change)})
    return out


YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline"


def _host(url: str) -> str:
    return re.sub(r"^www\.", "", urlparse(url).netloc)


@ttl_cache(seconds=30 * 60)
def news(symbol: str, limit: int = 20) -> list[dict]:
    """Yahoo headlines for one ticker. Ticker.news has come back empty since
    late 2026, so the per-ticker RSS feed comes first and Search is the fallback."""
    out = []
    try:
        r = httpx.get(YAHOO_RSS, params={"s": symbol, "region": "US", "lang": "en-US"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, follow_redirects=True)
        r.raise_for_status()
        for e in feedparser.parse(r.content).entries[:limit]:
            when = e.get("published_parsed")
            out.append(
                {
                    "title": e.get("title"),
                    "url": e.get("link"),
                    "source": _host(e.get("link") or ""),
                    "published": datetime(*when[:6], tzinfo=timezone.utc).isoformat() if when else None,
                }
            )
    except Exception as exc:
        log.warning("Yahoo RSS for %s failed: %s", symbol, exc)
    if not out:
        try:
            items = yf.Search(symbol, news_count=limit).news or []
        except Exception:
            items = []
        for item in items:
            ts = item.get("providerPublishTime")
            out.append(
                {
                    "title": item.get("title"),
                    "url": item.get("link"),
                    "source": item.get("publisher"),
                    "published": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
                }
            )
    return [n for n in out if n["title"] and n["url"]]


def _frame_records(df: pd.DataFrame | None, limit: int) -> list[dict]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    df = df.head(limit).copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%d")
    df = df.astype(object).where(pd.notna(df), None)
    return df.to_dict(orient="records")


@ttl_cache(seconds=6 * 60 * 60)
def ownership(symbol: str) -> dict:
    """Insider transactions and largest institutional holders (US 'supply/demand')."""
    t = yf.Ticker(symbol)
    result = {"insider_transactions": [], "institutional_holders": []}
    try:
        ins = t.insider_transactions
        if isinstance(ins, pd.DataFrame) and not ins.empty:
            keep = [c for c in ["Start Date", "Insider", "Position", "Transaction", "Text", "Shares", "Value"] if c in ins]
            result["insider_transactions"] = _frame_records(ins[keep], 20)
    except Exception as exc:
        log.info("insider_transactions(%s): %s", symbol, exc)
    try:
        holders = t.institutional_holders
        if isinstance(holders, pd.DataFrame) and not holders.empty:
            keep = [c for c in ["Holder", "pctHeld", "Shares", "Value", "pctChange", "Date Reported"] if c in holders]
            result["institutional_holders"] = _frame_records(holders[keep], 10)
    except Exception as exc:
        log.info("institutional_holders(%s): %s", symbol, exc)
    return result


@ttl_cache(seconds=6 * 60 * 60)
def annual_income(symbol: str) -> pd.DataFrame:
    """Annual income statement, rows = line items, columns = fiscal year ends."""
    try:
        df = yf.Ticker(symbol).income_stmt
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()
