from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter

from app.cache import ttl_cache
from app.indicators import _clean, pct_from_sma, percentile_rank, sparkline
from app.regime import read_regime
from app.services import calendar, fred, market, news, sentiment

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# id → where the number comes from and how to explain it.
INDICATORS = [
    {"id": "spx", "label": "S&P 500", "source": "yf", "symbol": "^GSPC", "unit": "pt", "change": "pct",
     "about": "미국 대형주 500개로 만든 대표 지수예요."},
    {"id": "vix", "label": "VIX", "source": "yf", "symbol": "^VIX", "unit": "", "change": "abs",
     "about": "S&P 500 옵션 가격으로 계산한 향후 30일 예상 변동성이에요. 높을수록 시장이 불안해한다는 뜻이에요."},
    {"id": "us10y", "label": "미국채 10년", "source": "fred", "symbol": "DGS10", "unit": "%", "change": "abs",
     "about": "장기 금리의 기준이에요. 오르면 주식, 특히 성장주의 할인율이 높아져요."},
    {"id": "curve", "label": "장단기 금리차", "source": "fred", "symbol": "T10Y2Y", "unit": "%p", "change": "abs",
     "about": "10년물 − 2년물 금리. 0 아래(역전)면 시장이 앞으로 금리 인하나 경기 둔화를 예상한다는 신호로 읽어요."},
    {"id": "dxy", "label": "달러 인덱스", "source": "yf", "symbol": "DX-Y.NYB", "unit": "", "change": "pct",
     "about": "주요 6개 통화 대비 달러 가치예요. 강달러는 미국 수출 기업과 신흥국에 부담이 돼요."},
    {"id": "wti", "label": "WTI 유가", "source": "yf", "symbol": "CL=F", "unit": "$", "change": "pct",
     "about": "미국 원유 선물 가격(배럴당 달러). 물가와 에너지 업종에 직접 영향을 줘요."},
    {"id": "hy", "label": "하이일드 스프레드", "source": "fred", "symbol": "BAMLH0A0HYM2", "unit": "%p", "change": "abs",
     "about": "신용등급이 낮은 회사채 금리와 국채 금리의 차이. 넓어지면 신용 위험을 걱정한다는 뜻이에요."},
]


def _series_for(spec: dict) -> pd.Series:
    if spec["source"] == "fred":
        return fred.series(spec["symbol"], years=5)
    df = market.history(spec["symbol"], period="5y")
    return df["Close"] if not df.empty else pd.Series(dtype=float)


def _change(s: pd.Series, days: int, how: str) -> float | None:
    s = s.dropna()
    if len(s) <= days:
        return None
    now, then = s.iloc[-1], s.iloc[-1 - days]
    return _clean((now / then - 1) * 100 if how == "pct" else now - then)


def _build(spec: dict) -> dict:
    base = {k: spec[k] for k in ("id", "label", "unit", "about")} | {"source": "FRED" if spec["source"] == "fred" else "Yahoo Finance"}
    try:
        s = _series_for(spec)
    except fred.FredUnavailable as exc:
        return base | {"error": str(exc)}
    except Exception as exc:
        log.warning("indicator %s failed: %s", spec["id"], exc)
        return base | {"error": "데이터를 불러오지 못했어요."}
    if s.empty:
        return base | {"error": "데이터가 없어요."}
    return base | {
        "value": _clean(s.iloc[-1]),
        "as_of": s.index[-1].strftime("%Y-%m-%d"),
        "change_kind": spec["change"],
        "change_1d": _change(s, 1, spec["change"]),
        "change_1m": _change(s, 21, spec["change"]),
        "percentile_5y": percentile_rank(s),
        "low_5y": _clean(s.min()),
        "high_5y": _clean(s.max()),
        "dist_sma200": pct_from_sma(s, 200) if spec["id"] == "spx" else None,
        "spark": sparkline(s.iloc[-63:]),
    }


@router.get("/indicators")
@ttl_cache(seconds=10 * 60)
def indicators() -> dict:
    with ThreadPoolExecutor(max_workers=6) as pool:
        items = list(pool.map(_build, INDICATORS))
        fg = pool.submit(sentiment.fear_greed).result()
    by_id = {i["id"]: i for i in items if "error" not in i}
    return {
        "indicators": items,
        "fear_greed": fg,
        "regime": read_regime(by_id),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@router.get("/sectors")
@ttl_cache(seconds=30 * 60)
def sectors() -> dict:
    from app.metrics import SECTORS

    symbols = tuple(list(market.SECTOR_ETFS) + ["SPY"])
    df = market.closes(symbols, period="6mo")
    if df.empty:
        return {"sectors": [], "error": "섹터 데이터를 불러오지 못했어요."}

    def ret(col: str, days: int) -> float | None:
        return _change(df[col], days, "pct") if col in df else None

    spy_1m = ret("SPY", 21)
    rows = []
    for etf, sector in market.SECTOR_ETFS.items():
        r1m = ret(etf, 21)
        rows.append(
            {
                "etf": etf,
                "sector": sector,
                "label": SECTORS.get(sector, sector),
                "ret_1w": ret(etf, 5),
                "ret_1m": r1m,
                "ret_3m": ret(etf, 63),
                "vs_spy_1m": _clean(r1m - spy_1m) if r1m is not None and spy_1m is not None else None,
            }
        )
    rows.sort(key=lambda r: r["ret_1m"] if r["ret_1m"] is not None else -999, reverse=True)
    return {"sectors": rows, "spy_1m": spy_1m}


@router.get("/week")
def week() -> dict:
    """This week's scheduled events and the latest market headlines."""
    cal = calendar.upcoming(days=7)
    return {"events": cal["events"], "notes": cal["notes"], "headlines": news.rss()[:12]}
