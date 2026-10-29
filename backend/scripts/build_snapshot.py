"""Build the daily screener snapshot.

    cd backend
    python -m scripts.build_snapshot            # S&P 500 + Nasdaq 100 (~10–20 min)
    python -m scripts.build_snapshot --limit 50 # quick test run
    python -m scripts.build_snapshot --refresh-universe
    python -m scripts.build_snapshot --fast     # skip annual statements (no CAGR / coverage)
    python -m scripts.build_snapshot --fresh    # start over instead of resuming an interrupted run

Progress is saved every 25 tickers, so an interrupted run continues where it stopped.
"""

from __future__ import annotations

import argparse
import sys
import time

from app.snapshot import build_snapshot, load_meta
from app.universe import load_universe, refresh_universe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="only the first N tickers")
    parser.add_argument("--refresh-universe", action="store_true", help="re-read index members from Wikipedia")
    parser.add_argument("--fast", action="store_true", help="skip annual income statements")
    parser.add_argument("--fresh", action="store_true", help="ignore progress saved by an interrupted run")
    args = parser.parse_args()

    if args.refresh_universe:
        print(f"universe: {len(refresh_universe())} tickers")
    symbols = load_universe()
    if args.limit:
        symbols = symbols[: args.limit]

    started = time.time()

    def progress(done: int, total: int, sym: str) -> None:
        sys.stdout.write(f"\r{done}/{total} {sym:<8}")
        sys.stdout.flush()

    df = build_snapshot(symbols, include_statements=not args.fast, progress=progress, resume=not args.fresh)
    print(f"\nsaved {len(df)} rows in {time.time() - started:.0f}s")
    meta = load_meta() or {}
    if meta.get("failed"):
        print(f"no data at all for {len(meta['failed'])}: {', '.join(meta['failed'][:20])}")
    if meta.get("no_prices"):
        print(f"no price history (RSI, returns empty) for {len(meta['no_prices'])}: {', '.join(meta['no_prices'][:20])}")


if __name__ == "__main__":
    main()
