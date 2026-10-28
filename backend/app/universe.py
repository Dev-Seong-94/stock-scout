"""Which tickers the screener covers.

Default: S&P 500 + Nasdaq 100 constituents, read from Wikipedia once and saved
to data/universe.csv. To use your own list instead, create data/universe.txt
with one ticker per line; it takes priority.
"""

from __future__ import annotations

import io
import logging

import httpx
import pandas as pd

from app.config import settings

log = logging.getLogger(__name__)

SOURCES = {
    "S&P 500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ["Symbol"], ["Security"]),
    "Nasdaq 100": ("https://en.wikipedia.org/wiki/Nasdaq-100", ["Ticker", "Symbol"], ["Company", "Security"]),
}

FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B", "JPM",
    "V", "UNH", "XOM", "LLY", "MA", "JNJ", "PG", "HD", "COST", "MRK",
]


def to_yahoo(symbol: str) -> str:
    """BRK.B → BRK-B (Yahoo uses dashes for share classes)."""
    return symbol.strip().upper().replace(".", "-")


def _read_table(url: str, ticker_cols: list[str], name_cols: list[str]) -> pd.DataFrame:
    html = httpx.get(url, headers={"User-Agent": "stock-scout/0.1 (personal research)"}, timeout=30).text
    for table in pd.read_html(io.StringIO(html)):
        tcol = next((c for c in ticker_cols if c in table.columns), None)
        ncol = next((c for c in name_cols if c in table.columns), None)
        if tcol and ncol and len(table) > 50:
            return pd.DataFrame({"ticker": table[tcol].map(to_yahoo), "name": table[ncol]})
    raise ValueError(f"No constituent table found at {url}")


def refresh_universe() -> pd.DataFrame:
    frames = []
    for index_name, (url, tcols, ncols) in SOURCES.items():
        try:
            df = _read_table(url, tcols, ncols)
            df["index"] = index_name
            frames.append(df)
        except Exception as exc:
            log.warning("Could not load %s: %s", index_name, exc)
    if not frames:
        raise RuntimeError("Wikipedia에서 종목 목록을 가져오지 못했어요.")
    df = pd.concat(frames).groupby("ticker", as_index=False).agg(
        name=("name", "first"), index=("index", lambda s: ", ".join(sorted(set(s))))
    )
    df.to_csv(settings.data_dir / "universe.csv", index=False)
    return df


def load_universe() -> list[str]:
    custom = settings.data_dir / "universe.txt"
    if custom.exists():
        tickers = [to_yahoo(line) for line in custom.read_text().splitlines() if line.strip() and not line.startswith("#")]
        return sorted(set(tickers))
    saved = settings.data_dir / "universe.csv"
    if saved.exists():
        return sorted(pd.read_csv(saved)["ticker"].dropna().unique().tolist())
    try:
        return sorted(refresh_universe()["ticker"].tolist())
    except Exception as exc:
        log.warning("Falling back to a small built-in list: %s", exc)
        return FALLBACK
