"use client";

import { useState } from "react";

import { InfoTip } from "@/components/ui";
import { metricValue, unitSuffix } from "@/lib/format";
import { useSavedPresets } from "@/lib/storage";
import { SECTOR_SUFFIX } from "@/lib/types";
import type { Catalog, Filters, Metric, Preset, Range } from "@/lib/types";

import { isActive, plainRange } from "./conditions";

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

/**
 * The left column: presets (load, save, delete), sector chips and every metric
 * as a min–max pair, grouped and searchable. Conditions live in the screener;
 * this only reports changes. Remount it (key) to reset which groups are open.
 */
export function FilterPanel({
  catalog,
  metricsByKey,
  filters,
  sectors,
  sectorMode,
  focus,
  open,
  onApplyPreset,
  onToggleSector,
  onSetRange,
  onSetMode,
  onReset,
}: {
  catalog: Catalog;
  metricsByKey: Map<string, Metric>;
  filters: Filters;
  sectors: string[];
  sectorMode: Record<string, boolean>;
  focus: string[];
  /** Shown on narrow screens only when opened. */
  open: boolean;
  onApplyPreset: (p: Preset) => void;
  onToggleSector: (key: string) => void;
  onSetRange: (key: string, r: Range) => void;
  onSetMode: (key: string, sector: boolean) => void;
  onReset: () => void;
}) {
  const [saved, setSaved] = useSavedPresets();
  const [presetName, setPresetName] = useState("");
  const [savingPreset, setSavingPreset] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const [metricQuery, setMetricQuery] = useState("");

  const activeKeys = Object.keys(filters).filter((k) => isActive(filters[k]));
  const presets: Preset[] = [...saved, ...catalog.presets.map((p) => ({ ...p, builtin: true }))];
  const mq = metricQuery.trim().toLowerCase();
  const matchesQuery = (m: Metric) => !mq || `${m.label} ${m.key} ${m.description}`.toLowerCase().includes(mq);

  const savePreset = () => {
    const name = presetName.trim();
    if (!name) return;
    const clean = Object.fromEntries(activeKeys.map((k) => [k, filters[k]]));
    setSaved((prev) => [{ id: `saved-${Date.now()}`, name, filters: clean, sectors }, ...prev.filter((p) => p.name !== name)]);
    setPresetName("");
    setSavingPreset(false);
  };

  return (
    <aside id="filters" className={`panel filters ${open ? "is-open" : ""}`} aria-label="필터">
      <div className="filters__top">
        <label className="filters__presets">
          <span className="small muted">프리셋</span>
          <select
            className="input"
            value=""
            onChange={(e) => {
              const p = presets.find((x) => x.id === e.target.value);
              if (p) onApplyPreset(p);
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
            <button className="btn btn--ghost" type="button" onClick={onReset}>
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
                onClick={() => onToggleSector(s.key)}
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

      {(focus.length && !mq ? [{ key: "mine", label: "내 기준으로 먼저 볼 지표" }, ...catalog.groups] : catalog.groups).map((g) => {
        const metrics =
          g.key === "mine"
            ? focus.map((k) => metricsByKey.get(k)).filter((m): m is Metric => !!m)
            : catalog.metrics.filter((m) => m.group === g.key && matchesQuery(m));
        if (mq && !metrics.length) return null;
        const count = metrics.filter((m) => isActive(filters[m.key]) || isActive(filters[m.key + SECTOR_SUFFIX])).length;
        const groupOpen = mq ? true : (openGroups[g.key] ?? (g.key === "mine" || count > 0));
        return (
          <div key={g.key} className="filters__group">
            <button
              type="button"
              className="filters__toggle"
              aria-expanded={groupOpen}
              onClick={() => setOpenGroups((o) => ({ ...o, [g.key]: !groupOpen }))}
            >
              <span>{g.label}</span>
              {count ? <span className="count">{count}</span> : <span className="small muted">{metrics.length}개</span>}
              <span className="chev" aria-hidden="true">
                {groupOpen ? "−" : "+"}
              </span>
            </button>
            {groupOpen ? (
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
                          onClick={() => onSetMode(m.key, !bySector)}
                        >
                          섹터 비교
                        </button>
                      </div>
                      <RangeInputs metric={m} sector={bySector} value={filters[key]} onChange={(r) => onSetRange(key, r)} />
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
  );
}
