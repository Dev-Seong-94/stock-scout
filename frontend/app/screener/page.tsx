"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { CriteriaSummary } from "@/components/MyCriteria";
import { CompareBar } from "@/components/screener/CompareBar";
import { baseKey, describeRange, isActive, plainRange, toCsv } from "@/components/screener/conditions";
import { FilterPanel } from "@/components/screener/FilterPanel";
import { PAGE_SIZE, ResultsTable } from "@/components/screener/ResultsTable";
import { SnapshotMissing } from "@/components/screener/SnapshotMissing";
import { StartHere } from "@/components/screener/StartHere";
import { ErrorNote, SetupHelp, Skeleton } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { focusMetrics } from "@/lib/criteria";
import { relativeTime } from "@/lib/format";
import { useProfile } from "@/lib/storage";
import { SECTOR_SUFFIX } from "@/lib/types";
import type { Catalog, Filters, Preset, Range, ScreenResult } from "@/lib/types";

const DEFAULT_COLUMNS = ["market_cap", "pe", "roe", "revenue_growth", "rsi14", "ret_3m"];
const STALE_DAYS = 3;

// Shown whenever a filter looks for stocks that fell a lot: the classic value trap.
const FALLEN_CHECKLIST = [
  "많이 빠진 종목은 이유가 있는 경우가 많아요. 최근 실적 발표·가이던스(공시의 8-K)와 뉴스를 먼저 확인하세요.",
  "실적 전망이 계속 낮아지는 중이면 싸 보여도 더 싸질 수 있어요(가치 함정).",
];

function Screener() {
  const router = useRouter();
  const params = useSearchParams();
  const catalogReq = useApi<Catalog>("/api/screener/metrics");
  const catalog = catalogReq.data;
  const [profile] = useProfile();

  const [filters, setFilters] = useState<Filters>({});
  const [sectors, setSectors] = useState<string[]>(() => (params.get("sector") ? [params.get("sector") as string] : []));
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("market_cap");
  const [desc, setDesc] = useState(true);
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<ScreenResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [skipStart, setSkipStart] = useState(false);
  const [showFilters, setShowFilters] = useState(false); // only matters on narrow screens
  const [sectorMode, setSectorMode] = useState<Record<string, boolean>>({});
  const [presetChecklist, setPresetChecklist] = useState<{ name: string; items: string[] } | null>(null);
  const [presetRun, setPresetRun] = useState(0); // remounts the filter panel so a preset's groups open

  const metricsByKey = useMemo(() => new Map((catalog?.metrics ?? []).map((m) => [m.key, m])), [catalog]);
  const activeKeys = Object.keys(filters).filter((k) => isActive(filters[k]));
  const focus = useMemo(() => (profile ? focusMetrics(profile) : []), [profile]);
  const baseColumns = profile ? ["market_cap", ...focus] : DEFAULT_COLUMNS;
  const columns = useMemo(() => [...new Set([...activeKeys.map(baseKey), ...baseColumns])].filter((k) => metricsByKey.has(k)), [activeKeys.join(), baseColumns.join(), metricsByKey]); // eslint-disable-line react-hooks/exhaustive-deps
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
          body: JSON.stringify({ filters: clean, sectors, query, sort, descending: desc, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
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
    setPresetRun((n) => n + 1);
  };

  const toggleSector = (key: string) => {
    setPage(0);
    setSectors((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]));
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

  const sectorLabel = new Map(catalog.sectors.map((s) => [s.key, s.label]));
  const builtAt = catalog.snapshot ? new Date(catalog.snapshot.built_at) : null;
  const staleDays = builtAt ? Math.floor((Date.now() - builtAt.getTime()) / 86400000) : 0;
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
        <div className="note small">
          <p>스크리너 데이터가 {staleDays}일 전 것이에요. 가격 지표(RSI, 수익률 등)가 지금과 다를 수 있어요.</p>
          <SetupHelp label="새로 만드는 방법">
            backend 폴더에서 <code>python -m scripts.build_snapshot</code>을 실행하세요. 전체는 45–60분쯤 걸려요.
          </SetupHelp>
        </div>
      ) : null}

      {!catalog.snapshot ? <SnapshotMissing catalog={catalog} onBuilt={catalogReq.reload} /> : null}

      <button type="button" className="btn filters-toggle" aria-expanded={showFilters} aria-controls="filters" onClick={() => setShowFilters((v) => !v)}>
        {showFilters ? "필터 닫기" : `필터 열기${activeKeys.length + sectors.length ? ` (${activeKeys.length + sectors.length})` : ""}`}
      </button>

      <div className="screener">
        <FilterPanel
          key={presetRun}
          catalog={catalog}
          metricsByKey={metricsByKey}
          filters={filters}
          sectors={sectors}
          sectorMode={sectorMode}
          focus={focus}
          open={showFilters}
          onApplyPreset={applyPreset}
          onToggleSector={toggleSector}
          onSetRange={setRange}
          onSetMode={setMode}
          onReset={reset}
        />

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
              profile={profile}
              onPick={applyPreset}
              onSkip={() => {
                setSkipStart(true);
                setShowFilters(true);
              }}
            />
          ) : null}

          {!showStart && profile ? <CriteriaSummary /> : null}

          {skipped.length ? (
            <div className="note small">
              <p>
                <b>{skipped.join(", ")}</b> 조건은 지금 데이터에 없어서 적용되지 않았어요. 새로 추가된 지표라 스냅샷을 다시 만들어야 해요.
              </p>
              <SetupHelp label="다시 만드는 방법">
                backend 폴더에서 <code>python -m scripts.build_snapshot --fresh</code>를 실행하세요.
              </SetupHelp>
            </div>
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

          <ResultsTable
            result={result}
            columns={columns}
            filteredColumns={filteredColumns}
            metricsByKey={metricsByKey}
            sectorLabel={sectorLabel}
            sort={sort}
            desc={desc}
            onSort={sortBy}
            page={page}
            onPage={setPage}
            remountKey={catalog.snapshot?.built_at ?? "no-snapshot"}
          />
        </section>
      </div>
      <CompareBar />
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
