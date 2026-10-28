"""Filtering the daily snapshot."""

from __future__ import annotations

import math
import threading

import pandas as pd

from app.metrics import METRIC_KEYS, METRICS
from app.snapshot import SNAPSHOT

_lock = threading.Lock()
_frame: pd.DataFrame | None = None

BASE_COLUMNS = ["symbol", "name", "sector", "industry", "price"]


def set_frame(df: pd.DataFrame | None) -> None:
    global _frame
    with _lock:
        _frame = df


def reload() -> None:
    set_frame(pd.read_parquet(SNAPSHOT) if SNAPSHOT.exists() else None)


def frame() -> pd.DataFrame | None:
    with _lock:
        loaded = _frame
    if loaded is None and SNAPSHOT.exists():
        reload()
        with _lock:
            loaded = _frame
    return loaded


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def apply_filters(
    df: pd.DataFrame,
    ranges: dict[str, list] | None = None,
    sectors: list[str] | None = None,
    query: str = "",
) -> pd.DataFrame:
    """ranges: {metric: [min|None, max|None]}. Rows missing a filtered metric are excluded."""
    mask = pd.Series(True, index=df.index)
    for key, bounds in (ranges or {}).items():
        if key not in METRIC_KEYS or key not in df.columns or not bounds:
            continue
        lo = _num(bounds[0]) if len(bounds) > 0 else None
        hi = _num(bounds[1]) if len(bounds) > 1 else None
        if lo is None and hi is None:
            continue
        col = pd.to_numeric(df[key], errors="coerce")
        mask &= col.notna()
        if lo is not None:
            mask &= col >= lo
        if hi is not None:
            mask &= col <= hi
    if sectors:
        mask &= df["sector"].isin(sectors)
    if query:
        q = query.strip().lower()
        mask &= df["symbol"].str.lower().str.contains(q, regex=False) | df["name"].fillna("").str.lower().str.contains(q, regex=False)
    return df[mask]


def _records(df: pd.DataFrame) -> list[dict]:
    clean = df.astype(object).where(pd.notna(df), None)
    out = clean.to_dict(orient="records")
    for row in out:
        for k, v in row.items():
            if isinstance(v, float):
                row[k] = round(v, 4)
    return out


def run(
    ranges: dict[str, list] | None = None,
    sectors: list[str] | None = None,
    query: str = "",
    sort: str = "market_cap",
    descending: bool = True,
    limit: int = 100,
    offset: int = 0,
    columns: list[str] | None = None,
) -> dict:
    df = frame()
    if df is None:
        return {"total": 0, "rows": [], "ready": False}
    result = apply_filters(df, ranges, sectors, query)
    if sort in result.columns:
        result = result.sort_values(sort, ascending=not descending, na_position="last")
    cols = BASE_COLUMNS + [c for c in (columns or [m.key for m in METRICS]) if c in result.columns and c not in BASE_COLUMNS]
    page = result.iloc[offset : offset + limit][cols]
    return {"total": int(len(result)), "rows": _records(page), "ready": True}


def distribution() -> dict[str, dict]:
    """10th/50th/90th percentile per metric, shown as hints beside each filter."""
    df = frame()
    if df is None:
        return {}
    out = {}
    for m in METRICS:
        if m.key not in df.columns:
            continue
        col = pd.to_numeric(df[m.key], errors="coerce").dropna()
        if col.empty:
            continue
        q = col.quantile([0.1, 0.5, 0.9])
        out[m.key] = {"p10": round(float(q[0.1]), 2), "p50": round(float(q[0.5]), 2), "p90": round(float(q[0.9]), 2), "count": int(len(col))}
    return out


def row(symbol: str) -> dict | None:
    df = frame()
    if df is None:
        return None
    hit = df[df["symbol"] == symbol.upper()]
    return _records(hit)[0] if not hit.empty else None


def sector_peers(sector: str | None) -> pd.DataFrame | None:
    df = frame()
    if df is None or not sector:
        return None
    return df[df["sector"] == sector]
