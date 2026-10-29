# Stock Scout — notes for Claude Code

Personal research tool for US stocks: look at the macro backdrop, then narrow
down stocks with indicator filters. It **does not recommend investments**; it
shows numbers with plain explanations and the user decides. Owner: Kihyeok
Seong (Korean, lives in Japan, frontend lead by day). Talk to him in Korean.

## Product decisions (keep these unless he asks otherwise)

- UI language is Korean, friendly 해요체. Every screener metric has a Korean
  explanation (what it measures / how to read it / pitfalls) in
  `backend/app/metrics.py`; the frontend renders it from `/api/screener/metrics`.
- Up/down colours default to the Korean convention (red up, blue down) and can
  be switched in the sidebar (`data-up` on `<html>`).
- No database. Personal data (watchlist, memos, filter presets, colour setting)
  lives in browser localStorage (`frontend/lib/storage.ts`) with JSON
  export/import. The server only caches public market data in memory and
  writes the screener snapshot files in `backend/data/`.
- The dashboard "시장 상태" summary is fixed rules (`backend/app/regime.py`),
  worded as description, never prediction or advice. Presets are labelled
  "예시 조합", not recommendations.
- Secrets go in `backend/.env` (template: `.env.example`), never committed.

## Architecture

```
backend/   FastAPI (Python 3.11 venv in backend/.venv)
  app/metrics.py      38 metrics + Korean text, sectors, example presets (+ checklists)
  app/indicators.py   RSI, SMA distance, returns, volatility, CAGR, performance_since (pure, tested)
  app/valuation.py    a stock's PER/PSR vs its own past (annual statements, pure, tested)
  app/snapshot.py     daily batch → data/snapshot.parquet (+ snapshot_meta.json)
  app/screener.py     filters the snapshot in memory; adds "<metric>@sector" percentile columns
  app/universe.py     which tickers the snapshot covers
  app/services/       fred, market (yfinance), sec, news (GDELT + RSS),
                      sentiment (CNN Fear & Greed, unofficial), calendar
  app/routers/        dashboard, screener, stocks, macro
  scripts/build_snapshot.py
  tests/test_core.py  offline tests (pytest -q)
frontend/  Next.js 16 App Router, React 19, plain CSS (app/globals.css tokens)
  app/page.tsx                 dashboard
  app/screener/page.tsx        filters + results table (rows clickable)
  app/stocks/[symbol]/page.tsx detail: chart, metric cards vs sector median, flow, news, filings
  app/macro/page.tsx           FRED trends, 30-day calendar, geopolitics (GDELT)
  app/watchlist/page.tsx       watchlist with reason/memo
  components/LineChart.tsx     hand-rolled SVG chart (no chart library)
```

Run: `cd backend && uvicorn app.main:app --reload --port 8000` and
`cd frontend && npm run dev`. Snapshot: `python -m scripts.build_snapshot`.

## Screener universe

S&P 500 + S&P 400 + S&P 600 + Nasdaq 100 from Wikipedia (`data/universe.csv`),
plus `data/universe_extra.txt` (user's own list: IONQ, INOD, RXRX, FIG, CRWV,
FRMI, SMR, JOBY, RKLB, BLSH, OPEN, ZETA …). `data/universe.txt`, if present,
replaces everything. Full build ≈ 45–60 min; progress is checkpointed every
25 tickers (`snapshot.partial.parquet`) and resumes automatically; `--fresh`
starts over, `--refresh-universe` re-reads Wikipedia.

## History of problems already fixed

- `[Errno 24] Too many open files` on macOS (limit 256): `snapshot.py` raises
  RLIMIT_NOFILE and imports pyarrow up front; results are checkpointed.
- RSI/returns were empty for most tickers: bulk `yf.download` now handles both
  column layouts, runs without threads, and falls back to per-ticker
  `Ticker.history`. `snapshot_meta.json` lists `failed` and `no_prices`.
- Nasdaq 100 was silently missing from the universe; reader made more lenient
  and now reports the columns it saw.

## Open items

1. **Nasdaq 100 still fails to load**: `could not load Nasdaq 100: no
   constituents table found (tables with 50+ rows had columns: [])` — the page
   fetched from https://en.wikipedia.org/wiki/Nasdaq-100 has no table with 50+
   rows, although Wikipedia mirrors from 2026-03 show a 101-row
   "Current components" table (Ticker | Company | ICB Industry | ICB Subsector).
   Next step: inspect what httpx actually receives (status, final URL, title,
   table sizes). As a stopgap, 12 Nasdaq-100 names outside the S&P 1500 were
   added to `universe_extra.txt`; remove them once fixed.
2. **`--prices-only` mode** (proposed, not built): refresh only price-based
   metrics (RSI, SMA, returns, volatility, rel. volume) from one bulk download
   and keep fundamentals from the existing snapshot. Daily run in ~1–2 min;
   full rebuild only in earnings season.
3. **Public deployment** (discussed, not decided): technically easy (Vercel +
   GitHub Actions cron + static snapshot JSON filtered in the browser), but
   Yahoo Finance data (yfinance) must not be redistributed publicly and CNN
   Fear & Greed is scraped. Options: public demo with sample data + private
   real-data deployment behind Vercel password protection, or switch to a
   licensed data API + SEC EDGAR for fundamentals.
4. `frontend/.env.local.example` could not be written by the previous tool;
   README documents `NEXT_PUBLIC_API_BASE` instead.

Verified 2026-10-29: `pytest -q` (13 passed), `npm run typecheck` and
`npm run build` all pass.

## Screener semantics (decided 2026-10-29)

- `Metric.positive_only` (PER, forward PER, PEG, PBR, PSR, EV/EBITDA): values
  ≤ 0 are losses / negative equity, not "cheap". They are dropped from filters,
  sector percentiles, medians and sorting, and shown as "음수" in the UI.
- Filter key `"<metric>@sector"` = percentile 0–100 within the stock's sector
  (0 = lowest value); sectors with < 5 usable values get none. Presets use it
  where absolute thresholds mislead across sectors (e.g. D/E for utilities).
- A filter on a metric that the current snapshot lacks is not silently dropped:
  `/api/screener/search` returns it in `skipped` and the UI says to rebuild.
- Yahoo returns `profitMargins = 0` for deeply negative margins; snapshot
  recomputes net margin from netIncomeToCommon / totalRevenue.
- "적자 성장주 점검" metrics: cash_runway (months; None when not burning cash),
  share_change_1y (diluted shares YoY), gross_margin_change (%p YoY). They need
  a full snapshot rebuild to appear in the screener.

## Conventions

- Keep metric definitions single-sourced in `metrics.py`; adding a metric means
  defining it there and computing it in `snapshot.build_row`.
- Keep `indicators.py` and the snapshot mapping pure and covered by tests.
- Design: cool grey paper `#eef1f4`, ink `#17212b`, indigo accent `#4b3fc9`,
  IBM Plex Sans KR, tabular numbers, dark mode via `prefers-color-scheme`.
  The dashboard's signature element is the 5-year range bar per indicator.
