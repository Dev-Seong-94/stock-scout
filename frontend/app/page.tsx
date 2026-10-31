"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";

import { Change, ErrorNote, InfoTip, RangeBar, Skeleton, Sparkline, Tabs } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dayLabel, num, relativeTime, signed } from "@/lib/format";
import type { Article, CalendarEvent, FearGreed, Indicator, IndicatorsResponse, InsiderFlow, InsiderName, MarginDebt, SectorRow } from "@/lib/types";

function percentileText(p: number | null | undefined) {
  if (p === null || p === undefined) return "";
  if (p >= 50) return `5년 중 상위 ${Math.max(1, Math.round(100 - p))}%`;
  return `5년 중 하위 ${Math.max(1, Math.round(p))}%`;
}

/** The signature element: where today's value sits inside its 5-year range. */
function IndicatorRange({ ind }: { ind: Indicator }) {
  if (ind.low_5y == null || ind.high_5y == null || ind.value == null) return null;
  return <RangeBar low={ind.low_5y} high={ind.high_5y} value={ind.value} middle={percentileText(ind.percentile_5y)} label="5년 범위" />;
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
          <IndicatorRange ind={ind} />
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

function usd(v: number) {
  if (v >= 1e9) return `$${num(v / 1e9, 1)}B`;
  if (v >= 1e6) return `$${num(v / 1e6, 1)}M`;
  if (v >= 1e3) return `$${num(v / 1e3, 0)}K`;
  return `$${num(v, 0)}`;
}

/** "평소보다 매도 비중이 높아요" when the ratio is clearly above or below the usual week. */
function compareRatio(ratio: number | null, usual: number | null | undefined) {
  if (ratio === null || !usual) return "";
  const diff = ratio / usual - 1;
  if (diff > 0.25) return "평소보다 매도 쪽으로 기울어 있어요.";
  if (diff < -0.25) return "평소보다 매수 비중이 높은 편이에요.";
  return "평소와 비슷한 수준이에요.";
}

function NameList({ title, rows }: { title: string; rows: InsiderName[] }) {
  return (
    <div>
      <h3 className="sub">{title}</h3>
      {rows.length ? (
        <ol className="flow-names">
          {rows.map((r) => (
            <li key={r.ticker}>
              <Link href={`/stocks/${r.ticker}`} className="ticker">
                {r.ticker}
              </Link>
              <span className="muted small flow-names__name">{r.name}</span>
              <span className="flow-names__value">{usd(r.value)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="small muted">최근 7일 기록이 없어요.</p>
      )}
    </div>
  );
}

function InsiderPanel() {
  const { data, error, loading, reload } = useApi<InsiderFlow>("/api/dashboard/insiders");
  const running = !!data?.status.running;
  // While the server is still collecting filings, check back now and then.
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(reload, 15000);
    return () => window.clearInterval(t);
  }, [running, reload]);

  const weeks = data?.weeks ?? [];
  const lastFull = [...weeks].reverse().find((w) => !w.partial);
  const base = data?.baseline;

  return (
    <section className="panel" aria-labelledby="insiders-title">
      <div className="panel__head">
        <h2 id="insiders-title">내부자 매매 (임원·이사·대주주)</h2>
        <InfoTip
          metric={{
            label: "내부자 매매",
            description: "미국 상장사 임원·이사·10% 대주주는 자기 회사 주식을 사고팔면 2영업일 안에 SEC에 Form 4를 내야 해요. 그걸 매주 모은 거예요.",
            reading: "주식 보상, 세금 납부용 반납, 증여는 빼고 시장에서 직접 사고판 것만 셌어요. 매도÷매수 배수가 평소보다 높으면 내부자들이 평소보다 많이 팔고 있다는 뜻이에요.",
            caveat: "내부자는 보상으로 받은 주식을 계속 팔기 때문에 평소에도 매도가 매수의 몇 배예요. 매도는 세금·분산 같은 개인 사정일 때가 많고, 매수가 더 드문 신호예요. 스크리너 종목 기준이에요.",
          }}
        />
      </div>
      <div className="panel__body">
        {error ? <ErrorNote message={error} onRetry={reload} /> : null}
        {loading && !data ? <Skeleton height={200} /> : null}
        {running ? (
          <p className="note small">
            SEC에서 최근 6주 공시를 모으는 중이에요 ({data!.status.done.toLocaleString()}/{data!.status.total.toLocaleString()}건 확인). 처음 한 번은 20–30분쯤
            걸리고, 그다음부터는 새로 나온 날만 받아요.
          </p>
        ) : null}
        {data?.status.error ? <p className="note small">{data.status.error}</p> : null}

        {lastFull ? (
          <p className="flow-lead">
            지난주(<span className="num">{lastFull.week.slice(5)}~</span>) 내부자 매도 <b>{lastFull.sell_filings}건</b> · 매수 <b>{lastFull.buy_filings}건</b>
            {lastFull.ratio !== null ? ` (매도가 매수의 ${lastFull.ratio}배)` : ""}. {compareRatio(lastFull.ratio, base?.ratio)}
          </p>
        ) : null}
        {base ? (
          <p className="small muted">
            평소({base.since.slice(0, 7)} ~ {base.until.slice(0, 7)} 주평균): 매도 {Math.round(base.sell_filings)}건 · 매수 {Math.round(base.buy_filings)}건
            {base.ratio !== null ? ` (${base.ratio}배)` : ""} · 매도 {usd(base.sell_value)} · 매수 {usd(base.buy_value)}
          </p>
        ) : null}

        {weeks.length ? (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="table">
              <thead>
                <tr>
                  <th className="left">주</th>
                  <th>매수 건수</th>
                  <th>매도 건수</th>
                  <th>매도÷매수</th>
                  <th>매수 금액</th>
                  <th>매도 금액</th>
                </tr>
              </thead>
              <tbody>
                {[...weeks].reverse().map((w) => (
                  <tr key={w.week}>
                    <td className="left">
                      {w.week.slice(5)}~{w.partial ? <span className="muted small"> 진행 중</span> : null}
                    </td>
                    <td>{w.buy_filings}</td>
                    <td>{w.sell_filings}</td>
                    <td>{w.ratio !== null ? `${w.ratio}배` : "–"}</td>
                    <td>{usd(w.buy_value)}</td>
                    <td>{usd(w.sell_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {data && (data.top_sells.length || data.top_buys.length) ? (
          <div className="flow-lists">
            <NameList title="최근 7일 많이 판 종목" rows={data.top_sells} />
            <NameList title="최근 7일 많이 산 종목" rows={data.top_buys} />
          </div>
        ) : null}
        <p className="small muted" style={{ marginTop: 10 }}>
          출처: SEC EDGAR Form 4. 공시일 기준으로 묶었어요.
        </p>
      </div>
    </section>
  );
}

function MarginPanel() {
  const { data, error, loading, reload } = useApi<MarginDebt>("/api/dashboard/margin");
  const fmt = (v: number) => (v >= 1000 ? `$${num(v / 1000, 2)}T` : `$${num(v, 0)}B`);
  return (
    <section className="panel" aria-labelledby="margin-title">
      <div className="panel__head">
        <h2 id="margin-title">개인 투자 분위기: 신용거래 잔고</h2>
        <InfoTip
          metric={{
            label: "신용거래 잔고",
            description: "투자자들이 증권사에서 돈을 빌려 주식을 산 금액의 합계예요(이른바 빚투). FINRA가 매달 발표해요.",
            reading: "빠르게 늘면 빚을 내서라도 사려는 낙관이 커지고 있다는 뜻이고, 줄면 위험을 줄이고 있다는 뜻이에요.",
            caveat: "개인만이 아니라 헤지펀드 등도 포함돼요. 한 달쯤 늦게 나오고, 주가가 오르면 잔고도 같이 커지는 경향이 있어요. 개인 '심리 설문'은 아니에요.",
          }}
        />
      </div>
      <div className="panel__body">
        {error ? <ErrorNote message={error} onRetry={reload} /> : null}
        {loading ? <Skeleton height={140} /> : null}
        {data ? (
          <>
            <p className="ind__value">
              {fmt(data.value)} <span className="small muted">{data.as_of} 기준</span>
            </p>
            <p className="small">
              전월 대비 <Change value={data.change_1m} digits={1} /> · 1년 전 대비 <Change value={data.change_1y} digits={1} />
            </p>
            <RangeBar
              low={data.low_5y}
              high={data.high_5y}
              value={data.value}
              middle={data.value >= data.high_5y ? "5년 중 최고" : "5년 범위"}
              label="신용거래 잔고 5년 범위"
              format={fmt}
            />
            <div className="margin-spark">
              <Sparkline values={data.points.map((p) => p[1])} width={320} height={56} />
              <p className="small muted">최근 10년 ({data.points[0][0]} ~ {data.as_of})</p>
            </div>
            <p className="small muted" style={{ marginTop: 10 }}>
              미국은 개인 순매수 금액을 공개하지 않아요. 개인 매매 데이터는 유료라서, 공식 무료 데이터 중 개인 투자 분위기를 가장 잘 보여주는 이 지표를 대신 보여줘요. 출처: FINRA.
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}

const KIND_LABEL = { fomc: "FOMC", economic: "지표", earnings: "실적" } as const;

const HEADLINES_SHOWN = 6; // the panel sits beside 이번 주 일정; keep the two about the same height

function ThisWeek() {
  const { data, error, loading, reload } = useApi<{ events: CalendarEvent[]; notes: string[]; headlines: Article[] }>("/api/dashboard/week");
  const [allNews, setAllNews] = useState(false);
  const headlines = data?.headlines ?? [];
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
            {(allNews ? headlines : headlines.slice(0, HEADLINES_SHOWN)).map((a) => (
              <li key={a.url}>
                <a className="article" href={a.url} target="_blank" rel="noreferrer">
                  <span className="article__title">{a.title}</span>
                  <span className="article__meta"> · {a.source} {relativeTime(a.published)}</span>
                </a>
              </li>
            ))}
          </ul>
          {headlines.length > HEADLINES_SHOWN ? (
            <button type="button" className="btn btn--ghost small" onClick={() => setAllNews((v) => !v)}>
              {allNews ? "접기" : `${headlines.length - HEADLINES_SHOWN}개 더 보기`}
            </button>
          ) : null}
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

      <div className="section-head">
        <h2>누가 사고 누가 파나</h2>
      </div>
      <div className="grid flows">
        <InsiderPanel />
        <MarginPanel />
      </div>

      <p className="disclaimer">
        숫자는 지난 5년 범위 안에서 지금 어디쯤인지를 보여줄 뿐, 앞으로의 방향을 말하지 않아요. 요약 문장은 고정된 규칙으로 만든 설명이에요.
      </p>
    </>
  );
}
