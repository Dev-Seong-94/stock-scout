from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.indicators import _clean
from app.services import calendar, fred, news

router = APIRouter(prefix="/api/macro", tags=["macro"])


@router.get("/groups")
def groups() -> dict:
    return {"groups": [{"key": g["key"], "label": g["label"]} for g in fred.MACRO_GROUPS]}


# Every period is cut from one long download per series, so switching
# 2y/5y/10y/20y never refetches from FRED.
MAX_YEARS = 30


def _one(item: dict, years: int) -> dict:
    try:
        s = fred.transform(fred.series(item["id"], years=MAX_YEARS + 1), item["how"])
        s = s[s.index >= s.index.max() - pd.DateOffset(years=years)]
    except fred.FredUnavailable:
        raise
    except Exception:
        return item | {"error": "데이터를 불러오지 못했어요.", "points": []}
    return item | {
        "latest": _clean(s.iloc[-1]) if len(s) else None,
        "as_of": s.index[-1].strftime("%Y-%m-%d") if len(s) else None,
        "points": [[d.strftime("%Y-%m-%d"), round(float(v), 3)] for d, v in s.items()],
    }


def warm() -> None:
    """Fetch every macro series once in the background so the first tab clicks are instant."""
    for group in fred.MACRO_GROUPS:
        for item in group["series"]:
            try:
                fred.series(item["id"], years=MAX_YEARS + 1)
            except fred.FredUnavailable:
                return
            except Exception:
                continue


@router.get("/series")
def series(group: str, years: int = Query(10, ge=1, le=MAX_YEARS)) -> dict:
    spec = next((g for g in fred.MACRO_GROUPS if g["key"] == group), None)
    if spec is None:
        raise HTTPException(404, "알 수 없는 그룹이에요.")
    # Fetch the group's series in parallel instead of one after another.
    with ThreadPoolExecutor(max_workers=len(spec["series"])) as pool:
        try:
            out = list(pool.map(lambda item: _one(item, years), spec["series"]))
        except fred.FredUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
    return {"group": spec["key"], "label": spec["label"], "series": out}


@router.get("/calendar")
def events(days: int = Query(30, ge=1, le=90), symbols: str = "") -> dict:
    wanted = tuple(s.strip().upper() for s in symbols.split(",") if s.strip())
    return calendar.upcoming(days=days, symbols=wanted)


@router.get("/geo/topics")
def geo_topics() -> dict:
    return {"topics": [{"key": t["key"], "label": t["label"]} for t in news.GEO_TOPICS]}


@router.get("/geo")
def geo(topic: str, timespan: str = "7d") -> dict:
    spec = next((t for t in news.GEO_TOPICS if t["key"] == topic), None)
    if spec is None:
        raise HTTPException(404, "알 수 없는 주제예요.")
    try:
        articles = news.gdelt(spec["query"], timespan=timespan)
    except news.GdeltUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"topic": spec["key"], "label": spec["label"], "articles": articles}
