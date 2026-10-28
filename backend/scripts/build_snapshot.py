"""Build the daily screener snapshot.

    cd backend
    python -m scripts.build_snapshot            # S&P 500 + Nasdaq 100 (~10–20 min)
    python -m scripts.build_snapshot --limit 50 # quick test run
    python -m scripts.build_snapshot --refresh-universe
    python -m scripts.build_snapshot --fast     # skip annual statements (no CAGR / coverage)
"""

from __future__ import annotations

import argparse
import sys
import time

from app.snapshot import build_snapshot
from app.universe import load_universe, refresh_universe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="only the first N tickers")
    parser.add_argument("--refresh-universe", action="store_true", help="re-read index members from Wikipedia")
    parser.add_argument("--fast", action="store_true", help="skip annual income statements")
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

    df = build_snapshot(symbols, include_statements=not args.fast, progress=progress)
    print(f"\nsaved {len(df)} rows in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
