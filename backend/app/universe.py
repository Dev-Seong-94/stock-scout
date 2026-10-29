"""Which tickers the screener covers.

Default: S&P 1500 (S&P 500 + MidCap 400 + SmallCap 600) plus the Nasdaq 100,
read from Wikipedia and saved to data/universe.csv.

    data/universe_extra.txt  tickers to ADD on top of the default list
                             (e.g. IONQ: unprofitable companies can't join S&P indices)
    data/universe.txt        tickers to use INSTEAD of the default list

One ticker per line; lines starting with # are ignored.
"""

from __future__ import annotations

import io
import logging
import re

import httpx
import pandas as pd

from app.config import settings

log = logging.getLogger(__name__)

SOURCES = {
    "S&P 500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "S&P 400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "S&P 600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
    "Nasdaq 100": "https://en.wikipedia.org/wiki/Nasdaq-100",
}

TICKER_COLUMNS = {"symbol", "ticker", "ticker symbol"}
NAME_COLUMNS = {"security", "company", "name"}

FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B", "JPM",
    "V", "UNH", "XOM", "LLY", "MA", "JNJ", "PG", "HD", "COST", "MRK",
]

UNIVERSE_CSV = settings.data_dir / "universe.csv"
EXTRA = settings.data_dir / "universe_extra.txt"
OVERRIDE = settings.data_dir / "universe.txt"


def to_yahoo(symbol: str) -> str:
    """BRK.B → BRK-B (Yahoo uses dashes for share classes)."""
    return symbol.strip().upper().replace(".", "-")


def _norm(col) -> str:
    """Column name without footnote marks, lower case ('Ticker[3]' → 'ticker')."""
    if isinstance(col, tuple):  # multi-row headers
        col = col[-1]
    return re.sub(r"\[.*?\]", "", str(col)).strip().lower()


def _match(table: pd.DataFrame, min_rows: int) -> pd.DataFrame | None:
    cols = {_norm(c): c for c in table.columns}
    tcol = next((cols[c] for c in cols if c in TICKER_COLUMNS), None)
    ncol = next((cols[c] for c in cols if c in NAME_COLUMNS), None)
    if tcol is None or ncol is None or len(table) < min_rows:
        return None
    tickers = table[tcol].astype(str).str.strip().map(to_yahoo)
    ok = tickers.str.fullmatch(r"[A-Z][A-Z0-9\-]{0,6}")
    return pd.DataFrame({"ticker": tickers[ok], "name": table[ncol][ok]})


def pick_constituents(tables: list[pd.DataFrame], min_rows: int = 50) -> pd.DataFrame:
    """Find the table that lists index members and return ticker/name columns."""
    for table in tables:
        found = _match(table, min_rows)
        if found is None and len(table) > min_rows:
            # Some tables put their header in a normal row; try that row as the header.
            promoted = table.iloc[1:].copy()
            promoted.columns = [str(v) for v in table.iloc[0]]
            found = _match(promoted, min_rows)
        if found is not None and len(found) >= min_rows:
            return found
    big = [[_norm(c) for c in t.columns][:6] for t in tables if len(t) >= min_rows]
    raise ValueError(f"no constituents table found (tables with {min_rows}+ rows had columns: {big})")


def _read_index(url: str) -> pd.DataFrame:
    headers = {"User-Agent": "stock-scout/0.1 (personal research tool)"}
    r = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return pick_constituents(pd.read_html(io.StringIO(r.text)))


def refresh_universe() -> pd.DataFrame:
    frames, problems = [], []
    for index_name, url in SOURCES.items():
        try:
            df = _read_index(url)
            df["index"] = index_name
            frames.append(df)
            log.info("%s: %d tickers", index_name, len(df))
        except Exception as exc:
            problems.append(f"{index_name}: {exc}")
    if not frames:
        raise RuntimeError("위키백과에서 종목 목록을 가져오지 못했어요. " + "; ".join(problems))
    for p in problems:
        log.warning("could not load %s", p)
    df = pd.concat(frames).groupby("ticker", as_index=False).agg(
        name=("name", "first"), index=("index", lambda s: ", ".join(sorted(set(s))))
    )
    df.to_csv(UNIVERSE_CSV, index=False)
    df.attrs["problems"] = problems
    return df


def _read_list(path) -> list[str]:
    if not path.exists():
        return []
    lines = (line.split("#")[0].strip() for line in path.read_text().splitlines())
    return [to_yahoo(line) for line in lines if line]


def _saved_is_current() -> bool:
    """universe.csv made before S&P 400/600 were added should be rebuilt."""
    if not UNIVERSE_CSV.exists():
        return False
    indexes = set(", ".join(pd.read_csv(UNIVERSE_CSV)["index"].dropna()).split(", "))
    return {"S&P 400", "S&P 600"} <= indexes


def load_universe() -> list[str]:
    if OVERRIDE.exists():
        return sorted(set(_read_list(OVERRIDE)))
    if _saved_is_current():
        base = pd.read_csv(UNIVERSE_CSV)["ticker"].dropna().tolist()
    else:
        try:
            base = refresh_universe()["ticker"].tolist()
        except Exception as exc:
            log.warning("Falling back to a small built-in list: %s", exc)
            base = FALLBACK
    return sorted(set(base) | set(_read_list(EXTRA)))


def describe_universe(symbols: list[str]) -> str:
    """One line for the build script: how many tickers came from where."""
    parts = []
    if OVERRIDE.exists():
        parts.append("universe.txt")
    elif UNIVERSE_CSV.exists():
        df = pd.read_csv(UNIVERSE_CSV)
        for name in SOURCES:
            n = int(df["index"].fillna("").str.contains(name, regex=False).sum())
            parts.append(f"{name} {n}")
        extra = [s for s in _read_list(EXTRA) if s not in set(df["ticker"])]
        if extra:
            parts.append(f"extra {len(extra)} ({', '.join(extra[:5])}{'…' if len(extra) > 5 else ''})")
    return f"universe: {len(symbols)} tickers — " + ", ".join(parts)
