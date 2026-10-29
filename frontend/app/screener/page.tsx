"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { ErrorNote, InfoTip, Skeleton, WatchStar } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { direction, metricCell, metricValue, price, relativeTime, unitSuffix } from "@/lib/format";
import { useSavedPresets, useWatchlist } from "@/lib/storage";
import { SECTOR_SUFFIX } from "@/lib/types";
import type { Catalog, Filters, Metric, Preset, Range, ScreenResult } from "@/lib/types";

const PAGE = 100;
const DEFAULT_COLUMNS = ["market_cap", "pe", "roe", "revenue_growth", "rsi14", "ret_3m"];
// Signed price moves get up/down colour; everything else stays neutral.
const SIGNED = new Set(["ret_1m", "ret_3m", "ret_6m", "ret_1y", "dist_sma50", "dist_sma200", "from_52w_high", "share_change_1y", "gross_margin_change"]);
const STALE_DAYS = 3;

const baseKey = (key: string) => (key.endsWith(SECTOR_SUFFIX) ? key.slice(0, -SECTOR_SUFFIX.length) : key);

// Shown whenever a filter looks for stocks that fell a lot: the classic value trap.
const FALLEN_CHECKLIST = [
  "많이 빠진 종목은 이유가 있는 경우가 많아요. 최근 실적 발표·가이던스(공시의 8-K)와 뉴스를 먼저 확인하세요.",
  "실적 전망이 계속 낮아지는 중이면 싸 보여도 더 싸질 수 있어요(가치 함정).",
];

function RangeInputs({
  metric,
  value,
  sector,
  onChange,
}: {
  metric: Metric;
  value: Range | undefined;
  sector: boolean;
  onChange: (r: Range) => void;
}) {
  const [lo, hi] = value ?? [null, null];
  const parse = (s: string) => (s.trim() === "" || s === "-" ? null : Number(s));
  const suffix = sector ? "%ile" : unitSuffix(metric.unit);
  return (
    <div className="range-inputs">
      <input
        className="input"
        type="number"
        inputMode="decimal"
        step={sector ? 5 : metric.step}
        min={sector ? 0 : undefined}
        max={sector ? 100 : undefined}
        aria-label={`${metric.label} ${sector ? "섹터 백분위 " : ""}최소`}
        placeholder={sector ? "0" : "최소"}
        value={lo ?? ""}
        onChange={(e) => onChange([parse(e.target.value), hi])}
      />
      <span className="muted" aria-hidden="true">
        ~
      </span>
      <input
        className="input"
        type="number"
        inputMode="decimal"
        step={sector ? 5 : metric.step}
        min={sector ? 0 : undefined}
        max={sector ? 100 : undefined}
        aria-label={`${metric.label} ${sector ? "섹터 백분위 " : ""}최대`}
        placeholder={sector ? "100" : "최대"}
        value={hi ?? ""}
        onChange={(e) => onChange([lo, parse(e.target.value)])}
      />
      <span className="range-inputs__unit muted small">{suffix}</span>
    </div>
  );
}

function isActive(r: Range | undefined) {
  return !!r && (r[0] !== null || r[1] !== null);
}

// Metrics where the sign carries the meaning (up/down, above/below). "최대 −20"
// reads backwards for them, so conditions are also said in words.
type Words = { subj: string; up: string; down: string; notUp: string; notDown: string; zeroUp: string; zeroDown: string; unit?: string };
const period = (subj: string): Words => ({
  subj,
  up: "오른",
  down: "떨어진",
  notUp: "오르지 않은",
  notDown: "떨어지지 않은",
  zeroUp: `${subj} 오른`,
  zeroDown: `${subj} 떨어진`,
});
const average = (line: string): Words => ({
  subj: `${line}보다`,
  up: "위에 있는",
  down: "아래에 있는",
  notUp: "위로 벗어나지 않은",
  notDown: "아래로 벗어나지 않은",
  zeroUp: `${line} 위에 있는`,
  zeroDown: `${line} 아래에 있는`,
});
const PLAIN: Record<string, Words> = {
  ret_1m: period("한 달간"),
  ret_3m: period("3개월간"),
  ret_6m: period("6개월간"),
  ret_1y: period("1년간"),
  dist_sma50: average("50일선"),
  dist_sma200: average("200일선"),
  from_52w_high: { subj: "고점보다", up: "", down: "빠진", notUp: "", notDown: "빠지지 않은", zeroUp: "고점에 있는", zeroDown: "고점보다 낮은" },
  share_change_1y: {
    subj: "주식 수가 1년간",
    up: "늘어난",
    down: "줄어든",
    notUp: "늘지 않은",
    notDown: "줄지 않은",
    zeroUp: "주식 수가 1년간 늘어난",
    zeroDown: "주식 수가 1년간 줄어든",
  },
  gross_margin_change: {
    subj: "매출총이익률이 1년간",
    up: "오른",
    down: "내린",
    notUp: "오르지 않은",
    notDown: "내리지 않은",
    zeroUp: "매출총이익률이 1년간 오른",
    zeroDown: "매출총이익률이 1년간 내린",
    unit: "%p",
  },
};

/** "고점보다 20% 이상 빠진 종목" for signed metrics; null when no wording fits. */
function plainRange(key: string, r: Range): string | null {
  const w = PLAIN[key];
  if (!w) return null;
  const u = w.unit ?? "%";
  const n = (v: number) => `${Math.abs(v)}${u}`;
  const [lo, hi] = r;
  let text: string | null = null;
  if (lo !== null && hi !== null) {
    if (hi <= 0 && lo < 0) text = hi === 0 ? `${w.subj} ${n(lo)} 이내로 ${w.down}` : `${w.subj} ${Math.abs(hi)}~${n(lo)} ${w.down}`;
    else if (lo >= 0 && hi > 0 && w.up) text = lo === 0 ? `${w.subj} ${n(hi)} 이내로 ${w.up}` : `${w.subj} ${lo}~${n(hi)} ${w.up}`;
  } else if (lo !== null) {
    text = lo > 0 ? (w.up ? `${w.subj} ${n(lo)} 이상 ${w.up}` : null) : lo === 0 ? w.zeroUp : `${w.subj} ${n(lo)} 넘게 ${w.notDown}`;
  } else if (hi !== null) {
    text = hi < 0 ? `${w.subj} ${n(hi)} 이상 ${w.down}` : hi === 0 ? w.zeroDown : w.notUp ? `${w.subj} ${n(hi)} 넘게 ${w.notUp}` : null;
  }
  return text ? `${text} 종목` : null;
}

function describeRange(key: string, r: Range, m: Metric) {
  const [lo, hi] = r;
  if (key.endsWith(SECTOR_SUFFIX)) {
    if (lo !== null && hi !== null) return `섹터 내 ${lo}–${hi}%ile`;
    if (lo !== null) return `섹터 상위 ${100 - lo}%`;
    return `섹터 하위 ${hi}%`;
  }
  if (lo !== null && hi !== null) return `${metricValue(lo, m.unit)} ~ ${metricValue(hi, m.unit)}`;
  if (lo !== null) return `${metricValue(lo, m.unit)} 이상`;
  return `${metricValue(hi, m.unit)} 이하`;
}

/** First screen: example combinations as a starting point instead of 38 empty filters. */
function StartHere({ presets, onPick, onSkip }: { presets: Preset[]; onPick: (p: Preset) => void; onSkip: () => void }) {
  return (
    <section className="panel start-here" aria-labelledby="start-here-title">
      <div className="start-here__head">
        <div>
          <h2 id="start-here-title">어디서 시작할까요?</h2>
          <p className="small muted">
            예시 조합을 하나 고르면 조건이 채워지고, 왼쪽에서 숫자를 바꿔 볼 수 있어요. 추천이 아니라 거르는 방법의 예시예요.
          </p>
        </div>
        <button type="button" className="btn btn--ghost small" onClick={onSkip}>
          직접 고를게요
        </button>
      </div>
      <ul className="start-here__list">
        {presets.map((p) => (
          <li key={p.id}>
            <button type="button" className="start-card" onClick={() => onPick(p)}>
              <b>{p.name}</b>
              {p.note ? <span className="small muted">{p.note}</span> : null}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function toCsv(rows: ScreenResult["rows"], columns: string[]) {
  const head = ["symbol", "name", "sector", "price", ...columns];
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [head.join(","), ...rows.map((r) => head.map((h) => esc(r[h])).join(","))].join("\n");
}

function SnapshotMissing({ catalog, onBuilt }: { catalog: Catalog; onBuilt: () => void }) {
  const [status, setStatus] = useState(catalog.status);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!status.running) return;
    const t = window.setInterval(async () => {
      const s = await api<{ status: Catalog["status"] }>("/api/screener/status").catch(() => null);
      if (!s) return;
      setStatus(s.status);
      if (!s.status.running) {
        window.clearInterval(t);
        if (!s.status.error) onBuilt();
      }
    }, 3000);
    return () => window.clearInterval(t);
  }, [status.running, onBuilt]);

  const start = async () => {
    setError(null);
    try {
      const r = await api<{ status: Catalog["status"] }>("/api/screener/refresh", { method: "POST" });
      setStatus(r.status);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="note">
      <p>
        <b>스크리너 데이터가 아직 없어요.</b> 종목 지표는 하루에 한 번 미리 계산해 두고 그걸 필터해요. 터미널에서{" "}
        <code>python -m scripts.build_snapshot</code>을 실행하거나 아래 버튼을 눌러 주세요. S&amp;P 500 + 나스닥 100 기준 10–20분
        정도 걸려요.
      </p>
      <p style={{ marginTop: 10 }}>
        {status.running ? (
          <span>
            만드는 중… {status.done}/{status.total}
          </span>
        ) : (
          <button className="btn btn--primary" type="button" onClick={start}>
            지금 만들기
          </button>
        )}
      </p>
      {status.error || error ? <p className="small" style={{ marginTop: 8 }}>오류: {status.error ?? error}</p> : null}
    </div>
  );
}

function Screener() {
  const router = useRouter();
  const params = useSearchParams();
  const catalogReq = useApi<Catalog>("/api/screener/metrics");
  const catalog = catalogReq.data;
  const watch = useWatchlist();
  const [saved, setSaved] = useSavedPresets();

  const [filters, setFilters] = useState<Filters>({});
  const [sectors, setSectors] = useState<string[]>(() => (params.get("sector") ? [params.get("sector") as string] : []));
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("market_cap");
  const [desc, setDesc] = useState(true);
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<ScreenResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [savingPreset, setSavingPreset] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const [metricQuery, setMetricQuery] = useState("");
  const [skipStart, setSkipStart] = useState(false);
  const [showFilters, setShowFilters] = useState(false); // only matters on narrow screens
  const [sectorMode, setSectorMode] = useState<Record<string, boolean>>({});
  const [presetChecklist, setPresetChecklist] = useState<{ name: string; items: string[] } | null>(null);

  const metricsByKey = useMemo(() => new Map((catalog?.metrics ?? []).map((m) => [m.key, m])), [catalog]);
  const activeKeys = Object.keys(filters).filter((k) => isActive(filters[k]));
  const columns = useMemo(() => [...new Set([...activeKeys.map(baseKey), ...DEFAULT_COLUMNS])].filter((k) => metricsByKey.has(k)), [activeKeys.join(), metricsByKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const filteredColumns = new Set(activeKeys.map(baseKey));
  // RSI capped low or price far below its high → looking at stocks that fell a lot.
  const lookingAtFallen =
    (filters.rsi14?.[1] ?? 100) <= 40 || (filters.from_52w_high?.[1] ?? 0) <= -20 || (filters.ret_3m?.[1] ?? 0) <= -15;

  // Search whenever conditions change (debounced while typing).
  useEffect(() => {
    if (!catalog) return;
    const t = window.setTimeout(async () => {
      setBusy(true);
      try {
        const clean = Object.fromEntries(activeKeys.map((k) => [k, filters[k]]));
        const r = await api<ScreenResult>("/api/screener/search", {
          method: "POST",
          body: JSON.stringify({ filters: clean, sectors, query, sort, descending: desc, limit: PAGE, offset: page * PAGE }),
        });
        setResult(r);
        setError(null);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    }, 300);
    return () => window.clearTimeout(t);
  }, [catalog, filters, sectors, query, sort, desc, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const setRange = useCallback((key: string, r: Range) => {
    setPage(0);
    setFilters((f) => ({ ...f, [key]: r }));
  }, []);

  const setMode = (key: string, sector: boolean) => {
    // Values and percentiles mean different things, so switching clears the range.
    setPage(0);
    setFilters((f) => {
      const next = { ...f };
      delete next[key];
      delete next[key + SECTOR_SUFFIX];
      return next;
    });
    setSectorMode((m) => ({ ...m, [key]: sector }));
  };

  const applyPreset = (p: Preset) => {
    setPage(0);
    setFilters(p.filters);
    setSectors(p.sectors ?? []);
    setSectorMode(Object.fromEntries(Object.keys(p.filters).filter((k) => k.endsWith(SECTOR_SUFFIX)).map((k) => [baseKey(k), true])));
    setPresetChecklist(p.checklist?.length ? { name: p.name, items: p.checklist } : null);
    const groups = new Set(Object.keys(p.filters).map((k) => metricsByKey.get(baseKey(k))?.group));
    setOpenGroups(Object.fromEntries([...groups].filter(Boolean).map((g) => [g as string, true])));
  };

  const savePreset = () => {
    const name = presetName.trim();
    if (!name) return;
    const clean = Object.fromEntries(activeKeys.map((k) => [k, filters[k]]));
    setSaved((prev) => [{ id: `saved-${Date.now()}`, name, filters: clean, sectors }, ...prev.filter((p) => p.name !== name)]);
    setPresetName("");
    setSavingPreset(false);
  };

  const reset = () => {
    setFilters({});
    setSectorMode({});
    setPresetChecklist(null);
    setSectors([]);
    setQuery("");
    setPage(0);
    router.replace("/screener");
  };

  const sortBy = (key: string) => {
    if (sort === key) setDesc((d) => !d);
    else {
      setSort(key);
      setDesc(true);
    }
    setPage(0);
  };

  const download = () => {
    if (!result) return;
    const blob = new Blob(["﻿" + toCsv(result.rows, columns)], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `stock-scout-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (catalogReq.error) return <ErrorNote message={catalogReq.error} onRetry={catalogReq.reload} />;
  if (!catalog) return <Skeleton height={400} />;

  const presets: Preset[] = [...saved, ...catalog.presets.map((p) => ({ ...p, builtin: true }))];
  const sectorLabel = new Map(catalog.sectors.map((s) => [s.key, s.label]));
  const builtAt = catalog.snapshot ? new Date(catalog.snapshot.built_at) : null;
  const staleDays = builtAt ? Math.floor((Date.now() - builtAt.getTime()) / 86400000) : 0;
  const mq = metricQuery.trim().toLowerCase();
  const matchesQuery = (m: Metric) => !mq || `${m.label} ${m.key} ${m.description}`.toLowerCase().includes(mq);
  const showStart = !skipStart && !activeKeys.length && !sectors.length && !query && !!catalog.snapshot;
  const skipped = (result?.skipped ?? []).map((k) => metricsByKey.get(baseKey(k))?.label ?? k);
  const checklist = presetChecklist?.items ?? (lookingAtFallen ? FALLEN_CHECKLIST : []);

  return (
    <>
      <div className="page-head">
        <h1>스크리너</h1>
        {builtAt && catalog.snapshot ? (
          <p className="small muted">
            {catalog.snapshot.count.toLocaleString()}개 종목 · 데이터 {builtAt.toLocaleDateString("ko-KR")} ({relativeTime(catalog.snapshot.built_at)}) 기준
          </p>
        ) : null}
      </div>

      {staleDays >= STALE_DAYS ? (
        <p className="note small">
          스크리너 데이터가 {staleDays}일 전 것이에요. 가격 지표(RSI, 수익률 등)가 지금과 다를 수 있어요. backend 폴더에서{" "}
          <code>python -m scripts.build_snapshot</code>으로 새로 만들 수 있어요.
        </p>
      ) : null}

      {!catalog.snapshot ? <SnapshotMissing catalog={catalog} onBuilt={catalogReq.reload} /> : null}

      <button type="button" className="btn filters-toggle" aria-expanded={showFilters} aria-controls="filters" onClick={() => setShowFilters((v) => !v)}>
        {showFilters ? "필터 닫기" : `필터 열기${activeKeys.length + sectors.length ? ` (${activeKeys.length + sectors.length})` : ""}`}
      </button>

      <div className="screener">
        <aside id="filters" className={`panel filters ${showFilters ? "is-open" : ""}`} aria-label="필터">
          <div className="filters__top">
            <label className="filters__presets">
              <span className="small muted">프리셋</span>
              <select
                className="input"
                value=""
                onChange={(e) => {
                  const p = presets.find((x) => x.id === e.target.value);
                  if (p) applyPreset(p);
                }}
              >
                <option value="">불러오기…</option>
                {saved.length ? (
                  <optgroup label="내 프리셋">
                    {saved.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
                <optgroup label="예시 조합">
                  {catalog.presets.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </optgroup>
              </select>
            </label>
            {savingPreset ? (
              <form
                className="filters__save"
                onSubmit={(e) => {
                  e.preventDefault();
                  savePreset();
                }}
              >
                <input className="input" autoFocus placeholder="프리셋 이름" value={presetName} onChange={(e) => setPresetName(e.target.value)} />
                <button className="btn btn--primary" type="submit" disabled={!presetName.trim()}>
                  저장
                </button>
                <button className="btn btn--ghost" type="button" onClick={() => setSavingPreset(false)}>
                  취소
                </button>
              </form>
            ) : (
              <div className="filters__actions">
                <button className="btn" type="button" onClick={() => setSavingPreset(true)} disabled={!activeKeys.length && !sectors.length}>
                  현재 조건 저장
                </button>
                <button className="btn btn--ghost" type="button" onClick={reset}>
                  초기화
                </button>
              </div>
            )}
            {saved.length ? (
              <details className="small">
                <summary className="muted">내 프리셋 관리 ({saved.length})</summary>
                <ul className="saved-presets">
                  {saved.map((p) => (
                    <li key={p.id}>
                      <span>{p.name}</span>
                      <button type="button" className="btn btn--ghost small" onClick={() => setSaved((prev) => prev.filter((x) => x.id !== p.id))}>
                        삭제
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>

          <div className="filters__group">
            <p className="filters__label">섹터</p>
            <div className="sector-chips">
              {catalog.sectors.map((s) => {
                const on = sectors.includes(s.key);
                return (
                  <button
                    key={s.key}
                    type="button"
                    className="sector-chip"
                    aria-pressed={on}
                    onClick={() => {
                      setPage(0);
                      setSectors((prev) => (on ? prev.filter((x) => x !== s.key) : [...prev, s.key]));
                    }}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="filters__find">
            <input
              className="input"
              type="search"
              placeholder="지표 찾기 (예: PER, 배당, 부채)"
              aria-label="지표 찾기"
              value={metricQuery}
              onChange={(e) => setMetricQuery(e.target.value)}
            />
          </div>

          {catalog.groups.map((g) => {
            const metrics = catalog.metrics.filter((m) => m.group === g.key && matchesQuery(m));
            if (mq && !metrics.length) return null;
            const count = metrics.filter((m) => isActive(filters[m.key]) || isActive(filters[m.key + SECTOR_SUFFIX])).length;
            const open = mq ? true : (openGroups[g.key] ?? count > 0);
            return (
              <div key={g.key} className="filters__group">
                <button
                  type="button"
                  className="filters__toggle"
                  aria-expanded={open}
                  onClick={() => setOpenGroups((o) => ({ ...o, [g.key]: !open }))}
                >
                  <span>{g.label}</span>
                  {count ? <span className="count">{count}</span> : <span className="small muted">{metrics.length}개</span>}
                  <span className="chev" aria-hidden="true">
                    {open ? "−" : "+"}
                  </span>
                </button>
                {open ? (
                  <ul className="filters__list">
                    {metrics.map((m) => {
                      const d = catalog.distribution[m.key];
                      const bySector = !!sectorMode[m.key];
                      const key = bySector ? m.key + SECTOR_SUFFIX : m.key;
                      return (
                        <li key={m.key} className={isActive(filters[key]) ? "is-active" : ""}>
                          <div className="filters__metric">
                            <span>{m.label}</span>
                            <InfoTip
                              metric={m}
                              extra={
                                d ? (
                                  <>
                                    <dt>지금 분포</dt>
                                    <dd>
                                      하위 10% {metricValue(d.p10, m.unit)} · 중앙값 {metricValue(d.p50, m.unit)} · 상위 10%{" "}
                                      {metricValue(d.p90, m.unit)} ({d.count.toLocaleString()}개 종목)
                                    </dd>
                                  </>
                                ) : null
                              }
                            />
                            {d && !bySector ? <span className="filters__median small muted">중앙 {metricValue(d.p50, m.unit)}</span> : null}
                            <button
                              type="button"
                              className="mode-toggle small"
                              aria-pressed={bySector}
                              title="같은 섹터 종목들 사이에서의 순위로 거르기 (0 = 가장 낮음, 100 = 가장 높음)"
                              onClick={() => setMode(m.key, !bySector)}
                            >
                              섹터 비교
                            </button>
                          </div>
                          <RangeInputs metric={m} sector={bySector} value={filters[key]} onChange={(r) => setRange(key, r)} />
                          {!bySector && isActive(filters[key]) && plainRange(key, filters[key]) ? (
                            <p className="filters__hint filters__plain small">→ {plainRange(key, filters[key])}</p>
                          ) : null}
                          {bySector ? (
                            <p className="filters__hint small muted">
                              같은 섹터 안 순위예요. 예: 최대 30 = {m.label} 낮은 쪽 30%, 최소 70 = 높은 쪽 30%.
                            </p>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </div>
            );
          })}
        </aside>

        <section className="results" aria-label="결과">
          <div className="results__bar">
            <input
              className="input results__search"
              type="search"
              placeholder="티커나 회사 이름으로 찾기"
              value={query}
              onChange={(e) => {
                setPage(0);
                setQuery(e.target.value);
              }}
            />
            <p className="results__count" aria-live="polite">
              {result ? (
                <>
                  <b>{result.total.toLocaleString()}</b>개 종목{busy ? " · 갱신 중" : ""}
                </>
              ) : (
                "검색 중"
              )}
            </p>
            <button className="btn" type="button" onClick={download} disabled={!result?.rows.length}>
              CSV 저장
            </button>
          </div>

          {activeKeys.length || sectors.length ? (
            <div className="active-chips">
              {sectors.map((s) => (
                <span key={s} className="chip">
                  {sectorLabel.get(s) ?? s}
                  <button type="button" aria-label={`${sectorLabel.get(s)} 섹터 조건 빼기`} onClick={() => setSectors((p) => p.filter((x) => x !== s))}>
                    ×
                  </button>
                </span>
              ))}
              {activeKeys.map((k) => {
                const m = metricsByKey.get(baseKey(k));
                return m ? (
                  <span key={k} className="chip">
                    {plainRange(k, filters[k]) ?? `${m.label} ${describeRange(k, filters[k], m)}`}
                    <button type="button" aria-label={`${m.label} 조건 빼기`} onClick={() => setRange(k, [null, null])}>
                      ×
                    </button>
                  </span>
                ) : null;
              })}
            </div>
          ) : null}

          {error ? <ErrorNote message={error} /> : null}

          {showStart ? (
            <StartHere
              presets={catalog.presets}
              onPick={applyPreset}
              onSkip={() => {
                setSkipStart(true);
                setShowFilters(true);
              }}
            />
          ) : null}

          {skipped.length ? (
            <p className="note small">
              <b>{skipped.join(", ")}</b> 조건은 지금 데이터에 없어서 적용되지 않았어요. 새로 추가된 지표라 스냅샷을 다시 만들어야 해요 (backend 폴더에서{" "}
              <code>python -m scripts.build_snapshot --fresh</code>).
            </p>
          ) : null}

          {checklist.length ? (
            <div className="note checklist">
              <p className="small">
                <b>{presetChecklist ? `'${presetChecklist.name}' 결과를 볼 때 확인할 것` : "많이 빠진 종목을 볼 때 확인할 것"}</b>
              </p>
              <ul className="small">
                {checklist.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="panel table-wrap results__table">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">종목</th>
                  <th scope="col" className="left">
                    섹터
                  </th>
                  <th scope="col">현재가</th>
                  {columns.map((k) => {
                    const m = metricsByKey.get(k)!;
                    return (
                      <th key={k} scope="col" aria-sort={sort === k ? (desc ? "descending" : "ascending") : undefined}>
                        <button type="button" className="sort-btn" aria-sort={sort === k ? (desc ? "descending" : "ascending") : undefined} onClick={() => sortBy(k)}>
                          {m.label}
                          {sort === k ? (desc ? " ↓" : " ↑") : ""}
                        </button>
                      </th>
                    );
                  })}
                  <th scope="col">
                    <span className="sr-only">관심</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {result?.rows.map((r) => (
                  <tr
                    key={r.symbol}
                    className="row-link"
                    onClick={(e) => {
                      // Let real links, buttons and text selection behave normally.
                      if ((e.target as HTMLElement).closest("a, button") || window.getSelection()?.toString()) return;
                      const href = `/stocks/${r.symbol}`;
                      if (e.metaKey || e.ctrlKey) window.open(href, "_blank");
                      else router.push(href);
                    }}
                  >
                    <td>
                      <Link className="ticker" href={`/stocks/${r.symbol}`}>
                        {r.symbol}
                      </Link>
                      <span className="results__name">{r.name}</span>
                      {r.other_classes ? <span className="results__name">같은 회사 다른 주식: {r.other_classes}</span> : null}
                    </td>
                    <td className="left muted">{sectorLabel.get(r.sector ?? "") ?? r.sector ?? "–"}</td>
                    <td>{price(r.price as number | null)}</td>
                    {columns.map((k) => (
                      <td
                        key={k}
                        className={`${filteredColumns.has(k) ? "is-filtered" : ""} ${SIGNED.has(k) ? direction(r[k] as number | null) : ""}`.trim() || undefined}
                      >
                        {metricCell(r[k] as number | null, metricsByKey.get(k)!)}
                      </td>
                    ))}
                    <td>
                      <WatchStar
                        symbol={r.symbol}
                        active={watch.has(r.symbol)}
                        onToggle={() =>
                          watch.has(r.symbol)
                            ? watch.remove(r.symbol)
                            : watch.add({ symbol: r.symbol, name: r.name, priceAtAdd: r.price as number | null })
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {result && result.ready && !result.rows.length ? (
              <p className="note" style={{ margin: 12 }}>
                조건에 맞는 종목이 없어요. 칩의 ×를 눌러 조건을 하나씩 풀어 보세요.
              </p>
            ) : null}
          </div>

          {result && result.total > PAGE ? (
            <div className="pager">
              <button className="btn" type="button" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                이전
              </button>
              <span className="small muted">
                {page * PAGE + 1}–{Math.min(result.total, (page + 1) * PAGE)} / {result.total.toLocaleString()}
              </span>
              <button className="btn" type="button" disabled={(page + 1) * PAGE >= result.total} onClick={() => setPage((p) => p + 1)}>
                다음
              </button>
            </div>
          ) : null}
        </section>
      </div>
    </>
  );
}

export default function ScreenerPage() {
  return (
    <Suspense fallback={<Skeleton height={400} />}>
      <Screener />
    </Suspense>
  );
}
