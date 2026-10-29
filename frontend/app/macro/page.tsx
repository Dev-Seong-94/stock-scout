"use client";

import { useMemo, useState } from "react";

import LineChart from "@/components/LineChart";
import { ErrorNote, Skeleton, Tabs } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dayLabel, num, relativeTime } from "@/lib/format";
import { useWatchlist } from "@/lib/storage";
import type { Article, CalendarEvent, MacroSeries } from "@/lib/types";

type Years = "2" | "5" | "10" | "20";

// Reference lines that make a chart easier to read.
const REFERENCE: Record<string, { value: number; label: string }> = {
  T10Y2Y: { value: 0, label: "역전 기준 0" },
  T10Y3M: { value: 0, label: "역전 기준 0" },
  PCEPILFE: { value: 2, label: "연준 목표 2%" },
  CPIAUCSL: { value: 2, label: "2%" },
  CPILFESL: { value: 2, label: "2%" },
  NFCI: { value: 0, label: "평균 0" },
};

function SeriesGrid() {
  const groups = useApi<{ groups: { key: string; label: string }[] }>("/api/macro/groups");
  const [group, setGroup] = useState("rates");
  const [years, setYears] = useState<Years>("5");
  const data = useApi<{ series: MacroSeries[] }>(`/api/macro/series?group=${group}&years=${years}`);

  return (
    <section aria-labelledby="trend-title">
      <div className="section-head">
        <h2 id="trend-title">추이</h2>
        <div className="section-head__tools">
          {groups.data ? (
            <Tabs label="분야" value={group} onChange={setGroup} options={groups.data.groups.map((g) => ({ value: g.key, label: g.label }))} />
          ) : null}
          <Tabs
            label="기간"
            value={years}
            onChange={setYears}
            options={[
              { value: "2", label: "2년" },
              { value: "5", label: "5년" },
              { value: "10", label: "10년" },
              { value: "20", label: "20년" },
            ]}
          />
        </div>
      </div>
      {data.error ? <ErrorNote message={data.error} onRetry={data.reload} /> : null}
      {/* Old charts stay visible while the next tab loads; dim them so the click visibly registered. */}
      <div className={`macro-grid ${data.loading && data.data ? "is-loading" : ""}`} aria-busy={data.loading}>
        {data.loading && !data.data
          ? Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="panel panel__body">
                <Skeleton height={200} />
              </div>
            ))
          : null}
        {data.data?.series.map((s) => (
          <article key={s.id} className="panel">
            <div className="panel__head">
              <h3>{s.label}</h3>
              <span className="macro-latest">
                {s.latest != null ? (
                  <>
                    <b>
                      {num(s.latest, s.unit === "K" || s.unit === "" ? 0 : 2)}
                      {s.unit === "%" || s.unit === "%p" ? s.unit : ""}
                    </b>{" "}
                    <span className="small muted">{s.as_of}</span>
                  </>
                ) : null}
              </span>
            </div>
            <div className="panel__body">
              {s.error ? (
                <p className="muted small">{s.error}</p>
              ) : (
                <LineChart
                  ariaLabel={`${s.label} 추이`}
                  dates={s.points.map((p) => p[0])}
                  series={[{ label: s.label, values: s.points.map((p) => p[1]), color: "var(--accent)" }]}
                  unit={s.unit === "%" || s.unit === "%p" ? s.unit : ""}
                  digits={s.unit === "K" || s.unit === "" ? 0 : 2}
                  height={180}
                  reference={REFERENCE[s.id]}
                />
              )}
              <p className="small muted">FRED {s.id}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

const KIND_LABEL = { fomc: "FOMC", economic: "지표", earnings: "실적" } as const;

function Calendar() {
  const watch = useWatchlist();
  const symbols = watch.items.map((i) => i.symbol).join(",");
  const { data, error, loading, reload } = useApi<{ events: CalendarEvent[]; notes: string[] }>(
    `/api/macro/calendar?days=30&symbols=${encodeURIComponent(symbols)}`,
  );
  const byDate = useMemo(() => {
    const m = new Map<string, CalendarEvent[]>();
    for (const e of data?.events ?? []) m.set(e.date, [...(m.get(e.date) ?? []), e]);
    return m;
  }, [data]);

  return (
    <section className="panel" id="calendar" aria-labelledby="cal-title">
      <div className="panel__head">
        <h2 id="cal-title">이벤트 캘린더 (30일)</h2>
      </div>
      <div className="panel__body">
        {error ? <ErrorNote message={error} onRetry={reload} /> : null}
        {loading ? <Skeleton height={200} /> : null}
        <ul className="events">
          {[...byDate.entries()].map(([date, events]) => (
            <li key={date}>
              <p className="events__date">{dayLabel(date)}</p>
              <ul>
                {events.map((e) => (
                  <li key={e.title}>
                    <span className={`tag tag--${e.kind}`}>{KIND_LABEL[e.kind]}</span> {e.title}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
        {data && !data.events.length ? <p className="muted small">예정된 이벤트가 없어요.</p> : null}
        {data?.notes.map((n) => (
          <p key={n} className="small muted" style={{ marginTop: 8 }}>
            {n}
          </p>
        ))}
        <p className="small muted" style={{ marginTop: 8 }}>
          실적 발표는 관심종목에 있는 종목만 보여줘요.
        </p>
      </div>
    </section>
  );
}

function Geo() {
  const topics = useApi<{ topics: { key: string; label: string }[] }>("/api/macro/geo/topics");
  const [topic, setTopic] = useState("trade");
  const { data, error, loading, reload } = useApi<{ articles: Article[] }>(`/api/macro/geo?topic=${topic}`);

  return (
    <section className="panel" id="geo" aria-labelledby="geo-title">
      <div className="panel__head geo-head">
        <h2 id="geo-title">지정학 이슈 (최근 7일)</h2>
        {topics.data ? (
          <Tabs label="주제" value={topic} onChange={setTopic} options={topics.data.topics.map((t) => ({ value: t.key, label: t.label }))} />
        ) : null}
      </div>
      <div className="panel__body">
        {error ? <ErrorNote message={error} onRetry={reload} /> : null}
        {loading ? <Skeleton height={240} /> : null}
        {data && !data.articles.length ? <p className="muted small">기사를 찾지 못했어요. GDELT가 잠시 응답하지 않을 수 있어요.</p> : null}
        <ul className="list-plain">
          {(data?.articles ?? []).map((a) => (
            <li key={a.url}>
              <a className="article" href={a.url} target="_blank" rel="noreferrer">
                <span className="article__title">{a.title}</span>
                <span className="article__meta">
                  {" "}
                  · {a.source} {relativeTime(a.published)}
                </span>
              </a>
            </li>
          ))}
        </ul>
        <p className="small muted" style={{ marginTop: 8 }}>
          출처: GDELT (전 세계 영문 기사 색인)
        </p>
      </div>
    </section>
  );
}

export default function MacroPage() {
  return (
    <>
      <div className="page-head">
        <h1>거시·정세</h1>
      </div>
      <div className="grid">
        <SeriesGrid />
        <div className="grid macro-lower">
          <Calendar />
          <Geo />
        </div>
      </div>
    </>
  );
}
