export type Tone = "calm" | "watch" | "stress";

export type Indicator = {
  id: string;
  label: string;
  unit: string;
  about: string;
  source: string;
  error?: string;
  value?: number | null;
  as_of?: string;
  change_kind?: "pct" | "abs";
  change_1d?: number | null;
  change_1m?: number | null;
  percentile_5y?: number | null;
  low_5y?: number | null;
  high_5y?: number | null;
  spark?: number[];
};

export type FearGreed = {
  value: number;
  rating: string;
  previous_week?: number;
  previous_month?: number;
  spark: number[];
} | null;

export type RegimeSignal = { label: string; tone: Tone; text: string };

export type IndicatorsResponse = {
  indicators: Indicator[];
  fear_greed: FearGreed;
  regime: RegimeSignal[];
  updated_at: string;
};

export type SectorRow = {
  etf: string;
  sector: string;
  label: string;
  ret_1w: number | null;
  ret_1m: number | null;
  ret_3m: number | null;
  vs_spy_1m: number | null;
};

export type CalendarEvent = {
  date: string;
  title: string;
  kind: "fomc" | "economic" | "earnings";
  symbol?: string;
  source?: string;
};

export type Article = {
  title: string;
  url: string;
  source?: string | null;
  published?: string | null;
};

export type Metric = {
  key: string;
  label: string;
  group: string;
  unit: string;
  description: string;
  reading: string;
  caveat: string;
  slider_min: number;
  slider_max: number;
  step: number;
  positive_only: boolean;
};

export type Range = [number | null, number | null];
/** Keys are metric keys, or "<metric>@sector" for the 0–100 percentile within the sector. */
export type Filters = Record<string, Range>;
export const SECTOR_SUFFIX = "@sector";

export type Preset = {
  id: string;
  name: string;
  note?: string;
  filters: Filters;
  sectors?: string[];
  checklist?: string[];
  builtin?: boolean;
};

export type Catalog = {
  groups: { key: string; label: string }[];
  metrics: Metric[];
  sectors: { key: string; label: string }[];
  presets: Preset[];
  distribution: Record<string, { p10: number; p50: number; p90: number; count: number }>;
  snapshot: { built_at: string; count: number; failed: string[] } | null;
  status: { running: boolean; done: number; total: number; error: string | null };
};

export type ScreenRow = {
  symbol: string;
  name: string | null;
  sector: string | null;
  industry: string | null;
  price: number | null;
  other_classes: string | null; // other share classes of the same company, e.g. "GOOG"
  [metric: string]: string | number | null;
};

export type ScreenResult = { total: number; rows: ScreenRow[]; ready: boolean; skipped?: string[] };

export type StockDetail = {
  symbol: string;
  name: string | null;
  sector: string | null;
  sector_label: string | null;
  industry: string | null;
  summary: string | null;
  website: string | null;
  employees: number | null;
  currency: string;
  price: number | null;
  change_pct: number | null;
  metrics: Record<string, number | null>;
  sector_median: Record<string, number>;
  sector_percentile: Record<string, number>;
  peer_count: number;
};

export type ValuationRange = {
  current: number | null;
  low: number;
  high: number;
  median: number;
  percentile: number | null;
  since: string;
  years: number;
};

export type Valuation = { pe: ValuationRange | null; ps: ValuationRange | null };

export type Performance = {
  symbol: string;
  since: string;
  base_date?: string;
  base_price?: number | null;
  change_pct?: number | null;
  benchmark_pct?: number | null;
  excess_pct?: number | null;
};

export type PriceHistory = {
  symbol: string;
  range: string;
  dates: string[];
  close: (number | null)[];
  volume: (number | null)[];
  sma_short: (number | null)[];
  sma_long: (number | null)[];
  sma_labels: [string, string];
};

export type Ownership = {
  short_float: number | null;
  short_ratio: number | null;
  insider_pct: number | null;
  institution_pct: number | null;
  insider_transactions: Record<string, string | number | null>[];
  institutional_holders: Record<string, string | number | null>[];
};

export type FilingSummary = { text: string; note: string; kind: "buy" | "sell" | "other" };
export type Filing = {
  form: string;
  label: string;
  date: string;
  description: string;
  url: string;
  summary: FilingSummary | null; // plain-Korean one-liner (Form 4, 144, 8-K)
  help: string; // what this kind of filing is
};

export type MacroSeries = {
  id: string;
  label: string;
  unit: string;
  how: string;
  latest?: number | null;
  as_of?: string | null;
  points: [string, number][];
  error?: string;
};

export type Quote = { symbol: string; price: number | null; change_pct: number | null };

export type WatchItem = {
  symbol: string;
  name?: string | null;
  addedAt: string;
  priceAtAdd?: number | null;
  reason: string;
  memo: string;
};
