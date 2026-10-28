from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.indicators import _clean
from app.services import calendar, fred, news

router = APIRouter(prefix="/api/macro", tags=["macro"])


@router.get("/groups")
def groups() -> dict:
    return {"groups": [{"key": g["key"], "label": g["label"]} for g in fred.MACRO_GROUPS]}


@router.get("/series")
def series(group: str, years: int = Query(10, ge=1, le=30)) -> dict:
    spec = next((g for g in fred.MACRO_GROUPS if g["key"] == group), None)
    if spec is None:
        raise HTTPException(404, "알 수 없는 그룹이에요.")
    out = []
    for item in spec["series"]:
        try:
            s = fred.transform(fred.series(item["id"], years=years + 1), item["how"])
            s = s[s.index >= s.index.max() - pd.DateOffset(years=years)]
        except fred.FredUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except Exception:
            out.append(item | {"error": "데이터를 불러오지 못했어요.", "points": []})
            continue
        out.append(
            item
            | {
                "latest": _clean(s.iloc[-1]) if len(s) else None,
                "as_of": s.index[-1].strftime("%Y-%m-%d") if len(s) else None,
                "points": [[d.strftime("%Y-%m-%d"), round(float(v), 3)] for d, v in s.items()],
            }
        )
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
    return {"topic": spec["key"], "label": spec["label"], "articles": news.gdelt(spec["query"], timespan=timespan)}
