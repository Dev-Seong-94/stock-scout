"""Filtering the daily snapshot."""

from __future__ import annotations

import math
import threading

import pandas as pd

from app.metrics import METRIC_KEYS, METRICS, SECTOR_SUFFIX
from app.snapshot import SNAPSHOT

_lock = threading.Lock()
_frame: pd.DataFrame | None = None
_loaded_mtime = 0.0  # snapshot file version currently in memory

BASE_COLUMNS = ["symbol", "name", "sector", "industry", "price", "other_classes"]
POSITIVE_ONLY = {m.key for m in METRICS if m.positive_only}
MIN_PEERS = 5  # fewer valid values than this in a sector → no percentile


def usable(df: pd.DataFrame, key: str) -> pd.Series:
    """A metric column as numbers, with meaningless values (≤ 0 multiples) as NaN."""
    col = pd.to_numeric(df[key], errors="coerce")
    return col.where(col > 0) if key in POSITIVE_ONLY else col


def with_sector_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """Add "<metric>@sector" columns: 0 = lowest in its sector, 100 = highest."""
    if "sector" not in df.columns:
        return df
    extra = {}
    for m in METRICS:
        if m.key not in df.columns:
            continue
        col = usable(df, m.key)
        groups = col.groupby(df["sector"])
        ranks = groups.rank(pct=True) * 100
        counts = groups.transform("count")
        extra[m.key + SECTOR_SUFFIX] = ranks.where(counts >= MIN_PEERS)
    return pd.concat([df, pd.DataFrame(extra, index=df.index)], axis=1)


def mark_share_classes(df: pd.DataFrame) -> pd.DataFrame:
    """One company listed as several share classes (GOOG/GOOGL, FOX/FOXA):
    keep the most traded as the primary row. The others get "share_class_of"
    and are left out of results, percentiles and medians so a company is not
    counted twice; the primary row lists them in "other_classes"."""
    df = df.copy()
    df["share_class_of"] = None
    df["other_classes"] = None
    if "name" not in df.columns:
        return df
    volume = pd.to_numeric(df.get("avg_dollar_volume"), errors="coerce").fillna(0) if "avg_dollar_volume" in df else pd.Series(0, index=df.index)
    named = df[df["name"].notna()]
    for _, idx in named.groupby("name").groups.items():
        if len(idx) < 2:
            continue
        ordered = volume.loc[idx].sort_values(ascending=False).index
        primary, rest = ordered[0], list(ordered[1:])
        df.loc[rest, "share_class_of"] = df.at[primary, "symbol"]
        df.at[primary, "other_classes"] = ", ".join(df.loc[rest, "symbol"])
    return df


def primary(df: pd.DataFrame) -> pd.DataFrame:
    """Rows without the secondary share classes."""
    return df[df["share_class_of"].isna()] if "share_class_of" in df.columns else df


def set_frame(df: pd.DataFrame | None) -> None:
    global _frame
    if df is not None:
        df = mark_share_classes(df)
        main = with_sector_percentiles(primary(df))
        # Secondary classes share the company's fundamentals: give them its percentiles.
        pct_cols = [c for c in main.columns if c.endswith(SECTOR_SUFFIX)]
        by_symbol = main.set_index("symbol")[pct_cols]
        rest = df[df["share_class_of"].notna()]
        rest = pd.concat([rest, by_symbol.reindex(rest["share_class_of"]).set_axis(rest.index)], axis=1)
        df = pd.concat([main, rest]).sort_index()
    with _lock:
        _frame = df


def reload() -> None:
    global _loaded_mtime
    mtime = SNAPSHOT.stat().st_mtime if SNAPSHOT.exists() else 0.0
    set_frame(pd.read_parquet(SNAPSHOT) if mtime else None)
    _loaded_mtime = mtime


def frame() -> pd.DataFrame | None:
    """The snapshot in memory, reloaded when the file was rebuilt (e.g. by
    scripts/build_snapshot.py in another process) so no server restart is needed."""
    with _lock:
        loaded = _frame
    if SNAPSHOT.exists() and (loaded is None or SNAPSHOT.stat().st_mtime > _loaded_mtime):
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
    """ranges: {metric: [min|None, max|None]}, or {"metric@sector": [0–100, 0–100]}
    for the percentile within the stock's sector. Rows missing a filtered
    metric (or with a meaningless ≤ 0 multiple) are excluded."""
    mask = pd.Series(True, index=df.index)
    for key, bounds in (ranges or {}).items():
        if key.removesuffix(SECTOR_SUFFIX) not in METRIC_KEYS or key not in df.columns or not bounds:
            continue
        lo = _num(bounds[0]) if len(bounds) > 0 else None
        hi = _num(bounds[1]) if len(bounds) > 1 else None
        if lo is None and hi is None:
            continue
        col = usable(df, key)
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
    # A search by name or ticker may look for a specific share class.
    result = apply_filters(df if query.strip() else primary(df), ranges, sectors, query)
    # Metrics added after the snapshot was built have no column yet; say so
    # instead of silently ignoring the condition.
    skipped = [k for k, b in (ranges or {}).items() if k not in df.columns and k.removesuffix(SECTOR_SUFFIX) in METRIC_KEYS and b and any(v is not None for v in b)]
    if sort in result.columns:
        result = result.assign(_sort=usable(result, sort)).sort_values("_sort", ascending=not descending, na_position="last")
    cols = [c for c in BASE_COLUMNS if c in result.columns] + [c for c in (columns or [m.key for m in METRICS]) if c in result.columns and c not in BASE_COLUMNS]
    page = result.iloc[offset : offset + limit][cols]
    return {"total": int(len(result)), "rows": _records(page), "ready": True, "skipped": skipped}


def distribution() -> dict[str, dict]:
    """10th/50th/90th percentile per metric, shown as hints beside each filter."""
    df = frame()
    if df is None:
        return {}
    df = primary(df)
    out = {}
    for m in METRICS:
        if m.key not in df.columns:
            continue
        col = usable(df, m.key).dropna()
        if col.empty:
            continue
        q = col.quantile([0.1, 0.5, 0.9])
        out[m.key] = {"p10": round(float(q[0.1]), 2), "p50": round(float(q[0.5]), 2), "p90": round(float(q[0.9]), 2), "count": int(len(col))}
    return out


def sector_percentiles(symbol: str) -> dict[str, float]:
    """Where this stock's snapshot values sit within its sector (0–100)."""
    df = frame()
    if df is None:
        return {}
    hit = df[df["symbol"] == symbol.upper()]
    if hit.empty:
        return {}
    out = {}
    for m in METRICS:
        v = hit.iloc[0].get(m.key + SECTOR_SUFFIX)
        if v is not None and not pd.isna(v):
            out[m.key] = round(float(v), 1)
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
    df = primary(df)
    return df[df["sector"] == sector]
