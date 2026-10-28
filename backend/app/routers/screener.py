from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import screener, snapshot
from app.metrics import metric_catalog
from app.universe import load_universe

router = APIRouter(prefix="/api/screener", tags=["screener"])


class SearchBody(BaseModel):
    filters: dict[str, list[float | None]] = Field(default_factory=dict)
    sectors: list[str] = Field(default_factory=list)
    query: str = ""
    sort: str = "market_cap"
    descending: bool = True
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)
    columns: list[str] | None = None


@router.get("/metrics")
def metrics() -> dict:
    """Metric definitions with Korean explanations, sectors, example presets,
    plus the current distribution of each metric across the universe."""
    return metric_catalog() | {
        "distribution": screener.distribution(),
        "snapshot": snapshot.load_meta(),
        "status": snapshot.status,
    }


@router.post("/search")
def search(body: SearchBody) -> dict:
    return screener.run(
        ranges=body.filters,
        sectors=body.sectors,
        query=body.query,
        sort=body.sort,
        descending=body.descending,
        limit=body.limit,
        offset=body.offset,
        columns=body.columns,
    )


@router.post("/refresh")
def refresh() -> dict:
    started = snapshot.start_background_build(load_universe())
    return {"started": started, "status": snapshot.status}


@router.get("/status")
def status() -> dict:
    return {"status": snapshot.status, "snapshot": snapshot.load_meta()}
