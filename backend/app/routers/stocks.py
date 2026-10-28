from __future__ import annotations

import re

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app import screener
from app.indicators import _clean
from app.metrics import METRICS, SECTORS
from app.services import market, news, sec
from app.snapshot import build_row

router = APIRouter(prefix="/api", tags=["stocks"])

SYMBOL = re.compile(r"^[A-Za-z0-9.\-^=]{1,15}$")

RANGES = {"1m": ("1mo", "1d"), "3m": ("3mo", "1d"), "6m": ("6mo", "1d"), "1y": ("1y", "1d"), "3y": ("3y", "1wk"), "5y": ("5y", "1wk")}


def _check(symbol: str) -> str:
    if not SYMBOL.match(symbol):
        raise HTTPException(400, "종목 코드 형식이 올바르지 않아요.")
    return symbol.upper()


@router.get("/stocks/{symbol}")
def detail(symbol: str) -> dict:
    symbol = _check(symbol)
    info = market.info(symbol)
    hist = market.history(symbol, period="2y")
    if not info and hist.empty:
        raise HTTPException(404, f"{symbol} 데이터를 찾지 못했어요.")

    # Fresh numbers for this one ticker (the snapshot may be a day old).
    metrics = build_row(symbol, hist, info, market.annual_income(symbol))

    # Sector medians from the snapshot, for context on each card.
    peers = screener.sector_peers(metrics.get("sector"))
    medians = {}
    if peers is not None and len(peers) >= 5:
        for m in METRICS:
            if m.key in peers:
                col = pd.to_numeric(peers[m.key], errors="coerce").dropna()
                if len(col) >= 5:
                    medians[m.key] = round(float(col.median()), 2)

    return {
        "symbol": symbol,
        "name": metrics.get("name"),
        "sector": metrics.get("sector"),
        "sector_label": SECTORS.get(metrics.get("sector") or "", metrics.get("sector")),
        "industry": metrics.get("industry"),
        "summary": info.get("longBusinessSummary"),
        "website": info.get("website"),
        "employees": info.get("fullTimeEmployees"),
        "currency": info.get("currency", "USD"),
        "price": metrics.get("price"),
        "change_pct": _clean(info.get("regularMarketChangePercent")),
        "metrics": {m.key: metrics.get(m.key) for m in METRICS},
        "sector_median": medians,
        "peer_count": int(len(peers)) if peers is not None else 0,
    }


@router.get("/stocks/{symbol}/history")
def history(symbol: str, range: str = Query("1y")) -> dict:
    symbol = _check(symbol)
    period, interval = RANGES.get(range, RANGES["1y"])
    # Load extra history so the 200-day average exists from the first visible bar.
    df = market.history(symbol, period="5y" if interval == "1d" else "10y", interval=interval)
    if df.empty:
        raise HTTPException(404, "가격 데이터가 없어요.")
    close = df["Close"]
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean() if interval == "1d" else close.rolling(40).mean()
    start = df.index.max() - pd.tseries.frequencies.to_offset(
        {"1mo": "30D", "3mo": "91D", "6mo": "182D", "1y": "365D", "3y": "1095D", "5y": "1826D"}[period]
    )
    view = df.index >= start

    def pts(s: pd.Series) -> list:
        return [None if pd.isna(v) else round(float(v), 4) for v in s[view]]

    return {
        "symbol": symbol,
        "range": range,
        "dates": [d.strftime("%Y-%m-%d") for d in df.index[view]],
        "close": pts(close),
        "volume": [int(v) if not pd.isna(v) else None for v in df["Volume"][view]],
        "sma_short": pts(sma50),
        "sma_long": pts(sma200),
        "sma_labels": ["50일선", "200일선"] if interval == "1d" else ["50주선", "40주선(≈200일)"],
    }


@router.get("/stocks/{symbol}/ownership")
def ownership(symbol: str) -> dict:
    symbol = _check(symbol)
    info = market.info(symbol)
    return {
        "short_float": _clean(info.get("shortPercentOfFloat")) and info["shortPercentOfFloat"] * 100,
        "short_ratio": _clean(info.get("shortRatio")),
        "insider_pct": _clean(info.get("heldPercentInsiders")) and info["heldPercentInsiders"] * 100,
        "institution_pct": _clean(info.get("heldPercentInstitutions")) and info["heldPercentInstitutions"] * 100,
        **market.ownership(symbol),
    }


@router.get("/stocks/{symbol}/news")
def stock_news(symbol: str) -> dict:
    symbol = _check(symbol)
    items = market.news(symbol)
    name = market.info(symbol).get("shortName")
    if name:
        cleaned = re.sub(r"\b(Inc\.?|Corporation|Corp\.?|Co\.?|Ltd\.?|plc|Holdings?|Class [A-C])\b", "", name).strip(" ,.")
        items += news.gdelt(f'"{cleaned}"', timespan="14d", limit=15)
    seen, out = set(), []
    for item in items:
        key = (item.get("title") or "").lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    out.sort(key=lambda i: i.get("published") or "", reverse=True)
    return {"articles": out[:30]}


@router.get("/stocks/{symbol}/filings")
def filings(symbol: str) -> dict:
    symbol = _check(symbol)
    try:
        return {"filings": sec.filings(symbol)}
    except sec.SecUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/quotes")
def quotes(symbols: str) -> dict:
    wanted = [_check(s.strip()) for s in symbols.split(",") if s.strip()][:100]
    return {"quotes": market.quotes(wanted)}


@router.get("/search")
def search(q: str) -> dict:
    """Ticker/name lookup inside the screener universe (for the search box)."""
    df = screener.frame()
    if df is None or not q.strip():
        return {"results": []}
    hits = screener.apply_filters(df, query=q)
    exact = hits[hits["symbol"] == q.strip().upper()]
    hits = pd.concat([exact, hits.drop(exact.index)]).head(10)[["symbol", "name", "sector"]]
    return {"results": hits.astype(object).where(pd.notna(hits), None).to_dict(orient="records")}
