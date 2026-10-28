"use client";

import Link from "next/link";
import { Fragment, useState } from "react";

import { Change, ErrorNote, InfoTip, Skeleton, Sparkline, Tabs } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dayLabel, num, relativeTime, signed } from "@/lib/format";
import type { Article, CalendarEvent, FearGreed, Indicator, IndicatorsResponse, SectorRow } from "@/lib/types";

function percentileText(p: number | null | undefined) {
  if (p === null || p === undefined) return "";
  if (p >= 50) return `5년 중 상위 ${Math.max(1, Math.round(100 - p))}%`;
  return `5년 중 하위 ${Math.max(1, Math.round(p))}%`;
}

/** The signature element: where today's value sits inside its 5-year range. */
function RangeBar({ ind }: { ind: Indicator }) {
  if (ind.low_5y == null || ind.high_5y == null || ind.value == null) return null;
  const span = ind.high_5y - ind.low_5y || 1;
  const pos = Math.min(100, Math.max(0, ((ind.value - ind.low_5y) / span) * 100));
  const digits = Math.abs(ind.high_5y) >= 100 ? 0 : 2;
  return (
    <div className="range" aria-label={`5년 범위 ${num(ind.low_5y, digits)}–${num(ind.high_5y, digits)}, ${percentileText(ind.percentile_5y)}`}>
      <div className="range__track">
        <span className="range__mark" style={{ left: `${pos}%` }} />
      </div>
      <div className="range__labels">
        <span>{num(ind.low_5y, digits)}</span>
        <span>{percentileText(ind.percentile_5y)}</span>
        <span>{num(ind.high_5y, digits)}</span>
      </div>
    </div>
  );
}

function IndicatorCard({ ind }: { ind: Indicator }) {
  const digits = ind.unit === "%" || ind.unit === "%p" ? 2 : (ind.value ?? 0) >= 1000 ? 0 : 2;
  const changeSuffix = ind.change_kind === "pct" ? "%" : ind.unit === "%" || ind.unit === "%p" ? "%p" : "";
  return (
    <article className="panel ind">
      <header className="ind__head">
        <h3>{ind.label}</h3>
        <InfoTip metric={{ label: ind.label, description: ind.about, reading: "", caveat: `출처: ${ind.source}${ind.as_of ? ` · ${ind.as_of} 기준` : ""}` }} />
      </header>
      {ind.error ? (
        <p className="muted small">{ind.error}</p>
      ) : (
        <>
          <div className="ind__value">
            <strong>
              {ind.unit === "$" ? "$" : ""}
              {num(ind.value, digits)}
              {ind.unit === "%" || ind.unit === "%p" ? <small>{ind.unit}</small> : null}
            </strong>
            <Sparkline values={ind.spark ?? []} width={84} height={28} />
          </div>
          <p className="ind__changes small">
            <span>
              1일 <Change value={ind.change_1d} suffix={changeSuffix} />
            </span>
            <span>
              1개월 <Change value={ind.change_1m} suffix={changeSuffix} />
            </span>
          </p>
          <RangeBar ind={ind} />
        </>
      )}
    </article>
  );
}

const FG_BANDS = [
  { to: 25, label: "극단적 공포" },
  { to: 45, label: "공포" },
  { to: 55, label: "중립" },
  { to: 75, label: "탐욕" },
  { to: 100, label: "극단적 탐욕" },
];

function FearGreedCard({ fg }: { fg: FearGreed }) {
  return (
    <article className="panel ind">
      <header className="ind__head">
        <h3>Fear &amp; Greed</h3>
        <InfoTip
          metric={{
            label: "Fear & Greed",
            description: "CNN이 모멘텀, 신고가·신저가, 풋콜 비율, 정크본드 수요, VIX 등 7개 지표로 만든 0–100 심리 지수예요.",
            reading: "25 이하 극단적 공포, 75 이상 극단적 탐욕. 역발상 참고 지표로 많이 봐요.",
            caveat: "CNN 비공식 데이터라 가끔 표시되지 않을 수 있어요.",
          }}
        />
      </header>
      {fg ? (
        <>
          <div className="ind__value">
            <strong>{Math.round(fg.value)}</strong>
            <span className="fg-rating">{fg.rating}</span>
          </div>
          <p className="ind__changes small">
            <span>1주 전 {fg.previous_week != null ? Math.round(fg.previous_week) : "–"}</span>
            <span>1개월 전 {fg.previous_month != null ? Math.round(fg.previous_month) : "–"}</span>
          </p>
          <div className="fg" aria-hidden="true">
            {FG_BANDS.map((b, i) => (
              <span key={b.label} className={`fg__band fg__band--${i}`} />
            ))}
            <span className="range__mark" style={{ left: `${fg.value}%` }} />
          </div>
          <div className="range__labels">
            <span>공포</span>
            <span>탐욕</span>
          </div>
        </>
      ) : (
        <p className="muted small">지금은 불러올 수 없어요. CNN이 데이터를 막았을 수 있어요.</p>
      )}
    </article>
  );
}

type SectorPeriod = "ret_1w" | "ret_1m" | "ret_3m";

function Sectors() {
  const { data, error, loading, reload } = useApi<{ sectors: SectorRow[]; spy_1m: number | null; error?: string }>("/api/dashboard/sectors");
  const [period, setPeriod] = useState<SectorPeriod>("ret_1m");
  const rows = [...(data?.sectors ?? [])].sort((a, b) => (b[period] ?? -999) - (a[period] ?? -999));
  const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r[period] ?? 0)));

  return (
    <section className="panel" aria-labelledby="sectors-title">
      <div className="panel__head">
        <h2 id="sectors-title">섹터 흐름</h2>
        <Tabs
          label="기간"
          value={period}
          onChange={setPeriod}
          options={[
            { value: "ret_1w", label: "1주" },
            { value: "ret_1m", label: "1개월" },
            { value: "ret_3m", label: "3개월" },
          ]}
        />
      </div>
      <div className="panel__body">
        {error ? <ErrorNote message={error} onRetry={reload} /> : null}
        {loading ? <Skeleton height={260} /> : null}
        <ul className="bars">
          {rows.map((r) => {
            const v = r[period] ?? 0;
            return (
              <li key={r.etf}>
                <Link href={`/screener?sector=${encodeURIComponent(r.sector)}`} className="bars__label" title={`${r.label} 종목을 스크리너에서 보기`}>
                  {r.label} <span className="muted small">{r.etf}</span>
                </Link>
                <span className="bars__track">
                  <span
                    className={`bars__fill ${v >= 0 ? "bars__fill--up" : "bars__fill--down"}`}
                    style={{ width: `${(Math.abs(v) / maxAbs) * 50}%`, [v >= 0 ? "left" : "right"]: "50%" }}
                  />
                </span>
                <Change value={r[period]} digits={1} className="bars__value" />
              </li>
            );
          })}
        </ul>
        {data?.spy_1m != null ? <p className="small muted">S&amp;P 500(SPY) 1개월 {signed(data.spy_1m, 1, "%")} · 섹터 이름을 누르면 스크리너로 이동해요.</p> : null}
      </div>
    </section>
  );
}

const KIND_LABEL = { fomc: "FOMC", economic: "지표", earnings: "실적" } as const;

function ThisWeek() {
  const { data, error, loading, reload } = useApi<{ events: CalendarEvent[]; notes: string[]; headlines: Article[] }>("/api/dashboard/week");
  const byDate = new Map<string, CalendarEvent[]>();
  for (const e of data?.events ?? []) byDate.set(e.date, [...(byDate.get(e.date) ?? []), e]);

  return (
    <div className="grid week">
      <section className="panel" aria-labelledby="events-title">
        <div className="panel__head">
          <h2 id="events-title">이번 주 일정</h2>
          <Link href="/macro#calendar" className="small muted">
            30일 일정
          </Link>
        </div>
        <div className="panel__body">
          {error ? <ErrorNote message={error} onRetry={reload} /> : null}
          {loading ? <Skeleton height={120} /> : null}
          {data && byDate.size === 0 ? <p className="muted small">7일 안에 예정된 주요 일정이 없어요.</p> : null}
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
          {data?.notes.map((n) => (
            <p key={n} className="small muted" style={{ marginTop: 8 }}>
              {n}
            </p>
          ))}
        </div>
      </section>
      <section className="panel" aria-labelledby="news-title">
        <div className="panel__head">
          <h2 id="news-title">시장 헤드라인</h2>
          <Link href="/macro#geo" className="small muted">
            지정학 이슈
          </Link>
        </div>
        <div className="panel__body">
          {loading ? <Skeleton height={160} /> : null}
          <ul className="list-plain">
            {(data?.headlines ?? []).map((a) => (
              <li key={a.url}>
                <a className="article" href={a.url} target="_blank" rel="noreferrer">
                  <span className="article__title">{a.title}</span>
                  <span className="article__meta"> · {a.source} {relativeTime(a.published)}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

export default function Dashboard() {
  const { data, error, loading, reload } = useApi<IndicatorsResponse>("/api/dashboard/indicators");

  return (
    <>
      <div className="page-head">
        <h1>시장 환경</h1>
        {data ? <p className="small muted">업데이트 {relativeTime(data.updated_at)}</p> : null}
      </div>

      {error ? <ErrorNote message={error} onRetry={reload} /> : null}

      <section className="regime" aria-label="지금 시장 상태 요약">
        {loading ? <Skeleton height={64} /> : null}
        {data?.regime.map((s) => (
          <p key={s.label} className={`regime__item regime__item--${s.tone}`}>
            <b>{s.label}</b> {s.text}
          </p>
        ))}
      </section>

      <section className="indicators" aria-label="주요 지표">
        {loading
          ? Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="panel ind">
                <Skeleton height={110} />
              </div>
            ))
          : null}
        {data?.indicators.map((ind) => (
          <Fragment key={ind.id}>
            <IndicatorCard ind={ind} />
            {ind.id === "vix" ? <FearGreedCard fg={data.fear_greed} /> : null}
          </Fragment>
        ))}
      </section>

      <div className="grid dash-lower">
        <Sectors />
        <ThisWeek />
      </div>

      <p className="disclaimer">
        숫자는 지난 5년 범위 안에서 지금 어디쯤인지를 보여줄 뿐, 앞으로의 방향을 말하지 않아요. 요약 문장은 고정된 규칙으로 만든 설명이에요.
      </p>
    </>
  );
}
