"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import LineChart from "@/components/LineChart";
import { Change, ErrorNote, InfoTip, RangeBar, Skeleton, Tabs } from "@/components/ui";
import { useApi } from "@/lib/api";
import { metricCell, metricValue, num, price, relativeTime, sectorRank } from "@/lib/format";
import { notables } from "@/lib/notables";
import { useWatchlist } from "@/lib/storage";
import type { Article, Catalog, Filing, Ownership, PriceHistory, StockDetail, Valuation, ValuationRange } from "@/lib/types";

type RangeKey = "1m" | "3m" | "6m" | "1y" | "3y" | "5y";
type TabKey = "flow" | "news" | "filings";

function PriceChart({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<RangeKey>("1y");
  const { data, error, loading } = useApi<PriceHistory>(`/api/stocks/${symbol}/history?range=${range}`);
  const first = data?.close.find((v) => v !== null) ?? null;
  const last = data ? [...data.close].reverse().find((v) => v !== null) ?? null : null;
  const change = first && last ? (last / first - 1) * 100 : null;

  return (
    <section className="panel" aria-labelledby="chart-title">
      <div className="panel__head">
        <h2 id="chart-title">
          주가 <Change value={change} digits={1} className="small" />
        </h2>
        <Tabs
          label="기간"
          value={range}
          onChange={setRange}
          options={(["1m", "3m", "6m", "1y", "3y", "5y"] as RangeKey[]).map((r) => ({
            value: r,
            label: { "1m": "1개월", "3m": "3개월", "6m": "6개월", "1y": "1년", "3y": "3년", "5y": "5년" }[r],
          }))}
        />
      </div>
      <div className="panel__body">
        {error ? <ErrorNote message={error} /> : null}
        {loading && !data ? <Skeleton height={280} /> : null}
        {data ? (
          <LineChart
            ariaLabel={`${symbol} 주가 차트`}
            dates={data.dates}
            height={280}
            digits={2}
            series={[
              { label: "종가", values: data.close, color: "var(--ink)", width: 2 },
              { label: data.sma_labels[0], values: data.sma_short, color: "var(--accent)", width: 1.25 },
              { label: data.sma_labels[1], values: data.sma_long, color: "var(--watch)", width: 1.25, dashed: true },
            ]}
          />
        ) : null}
      </div>
    </section>
  );
}

function MetricCards({ detail, catalog }: { detail: StockDetail; catalog: Catalog }) {
  return (
    <section aria-labelledby="metrics-title">
      <div className="section-head">
        <h2 id="metrics-title">지표</h2>
        {detail.peer_count ? (
          <p className="small muted">
            회색 숫자는 같은 섹터({detail.sector_label}) {detail.peer_count}개 종목의 중앙값이고, 그 아래는 섹터 안 순위예요 (스크리너 데이터 기준).
          </p>
        ) : null}
      </div>
      {catalog.groups.map((g) => (
        <div key={g.key} className="metric-group">
          <h3>{g.label}</h3>
          <div className="metric-cards">
            {catalog.metrics
              .filter((m) => m.group === g.key)
              .map((m) => {
                const v = detail.metrics[m.key];
                const med = detail.sector_median[m.key];
                const rank = detail.sector_percentile?.[m.key];
                return (
                  <div key={m.key} className="metric-card">
                    <div className="metric-card__label">
                      <span>{m.label}</span>
                      <InfoTip metric={m} />
                    </div>
                    <p className="metric-card__value" title={m.positive_only && v != null && v <= 0 ? "적자 또는 자본잠식이라 이 배수는 의미가 없어요" : undefined}>
                      {metricCell(v, m)}
                    </p>
                    {med !== undefined ? <p className="metric-card__median">섹터 {metricValue(med, m.unit)}</p> : null}
                    {rank !== undefined ? <p className="metric-card__rank">{sectorRank(rank)}</p> : null}
                  </div>
                );
              })}
          </div>
        </div>
      ))}
    </section>
  );
}

function AtAGlance({ detail, catalog, onReadFilings }: { detail: StockDetail; catalog: Catalog; onReadFilings: () => void }) {
  const items = notables(detail, catalog.metrics);
  return (
    <section className="panel glance" aria-labelledby="glance-title">
      <div className="panel__head">
        <h2 id="glance-title">한눈에 보기</h2>
        <span className="small muted">정해진 규칙으로 뽑은 사실이에요. 좋고 나쁨의 판단은 아니에요.</span>
      </div>
      <div className="panel__body">
        {items.length ? (
          <ul className="glance__list">
            {items.map((n) => (
              <li key={n.text} className={n.watch ? "is-watch" : undefined}>
                {n.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="small muted">섹터 안에서 특별히 튀는 숫자는 없어요.</p>
        )}
        <p className="glance__next small">
          <b>다음 단계</b> 숫자는 출발점이에요. 회사가 직접 쓴 최근 분기 보고서(10-Q)나 실적 발표(8-K)를 한 번은 읽어 보세요.{" "}
          <button type="button" className="btn btn--ghost small" onClick={onReadFilings}>
            공시 보기
          </button>
        </p>
      </div>
    </section>
  );
}

function ownHistoryText(r: ValuationRange) {
  if (r.percentile === null) return "";
  const p = r.percentile;
  return p >= 50 ? `${r.years}년 중 상위 ${Math.max(1, Math.round(100 - p))}%` : `${r.years}년 중 하위 ${Math.max(1, Math.round(p))}%`;
}

function OwnValuation({ label, unit, range }: { label: string; unit: string; range: ValuationRange | null }) {
  return (
    <div>
      <h3>
        <span>{label}</span>
        <span>{range?.current != null ? metricValue(range.current, unit) : "–"}</span>
      </h3>
      {range && range.current != null ? (
        <>
          <RangeBar
            low={range.low}
            high={range.high}
            value={range.current}
            middle={ownHistoryText(range)}
            label={`${label} 과거 범위`}
            format={(v) => metricValue(v, unit)}
          />
          <p className="small muted">
            {range.since.slice(0, 4)}년 이후 중앙값 {metricValue(range.median, unit)}
          </p>
        </>
      ) : range ? (
        <p className="small muted">최근 회계연도가 적자라 지금 값이 없어요. 과거 범위: {metricValue(range.low, unit)}–{metricValue(range.high, unit)}</p>
      ) : (
        <p className="small muted">
          {label === "PER" ? "최근 몇 년 대부분 적자였거나 실적 데이터가 부족해서 계산할 수 없어요. 적자 기업은 PSR을 보세요." : "계산할 만큼의 과거 실적 데이터가 없어요."}
        </p>
      )}
    </div>
  );
}

function ValuationHistory({ symbol }: { symbol: string }) {
  const { data, error, loading } = useApi<Valuation>(`/api/stocks/${symbol}/valuation`);
  return (
    <section className="panel" aria-labelledby="own-valuation-title">
      <div className="panel__head">
        <h2 id="own-valuation-title">자기 과거와 비교한 밸류에이션</h2>
      </div>
      <div className="panel__body">
        {error ? <ErrorNote message={error} /> : null}
        {loading && !data ? <Skeleton height={80} /> : null}
        {data ? (
          <>
            <div className="valuation-ranges">
              <OwnValuation label="PER" unit="x" range={data.pe} />
              <OwnValuation label="PSR" unit="x" range={data.ps} />
            </div>
            <p className="small muted" style={{ marginTop: 12 }}>
              매주 주가를 그 시점에 발표돼 있던 연간 실적으로 나눈 값이에요. 연간 실적 기준이라 위 카드(최근 12개월)와 조금 달라요. 과거보다 높다고 꼭
              비싼 건 아니에요: 성장 속도나 금리가 달라졌을 수 있어요.
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}

function Flow({ symbol }: { symbol: string }) {
  const { data, error, loading } = useApi<Ownership>(`/api/stocks/${symbol}/ownership`);
  if (error) return <ErrorNote message={error} />;
  if (loading || !data) return <Skeleton height={200} />;
  return (
    <div className="grid">
      <dl className="flow-stats">
        <div>
          <dt>공매도 비율</dt>
          <dd>{metricValue(data.short_float, "%")}</dd>
        </div>
        <div>
          <dt>공매도 상환일수</dt>
          <dd>{data.short_ratio != null ? `${num(data.short_ratio, 1)}일` : "–"}</dd>
        </div>
        <div>
          <dt>내부자 보유</dt>
          <dd>{metricValue(data.insider_pct, "%")}</dd>
        </div>
        <div>
          <dt>기관 보유</dt>
          <dd>{metricValue(data.institution_pct, "%")}</dd>
        </div>
      </dl>
      <p className="small muted">
        미국은 한국처럼 외국인·기관 일별 순매수가 공개되지 않아요. 대신 내부자 거래(Form 4), 기관 보유(13F), 공매도 잔고로 수급을 봐요.
      </p>

      <h3 className="sub">최근 내부자 거래</h3>
      {data.insider_transactions.length ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>날짜</th>
                <th className="left">내부자</th>
                <th className="left">직위</th>
                <th className="left">내용</th>
                <th>주식 수</th>
                <th>금액</th>
              </tr>
            </thead>
            <tbody>
              {data.insider_transactions.map((t, i) => (
                <tr key={i}>
                  <td>{String(t["Start Date"] ?? "")}</td>
                  <td className="left">{String(t.Insider ?? "")}</td>
                  <td className="left muted">{String(t.Position ?? "")}</td>
                  <td className="left">{String(t.Text || t.Transaction || "")}</td>
                  <td>{t.Shares != null ? num(Number(t.Shares), 0) : "–"}</td>
                  <td>{t.Value ? `$${num(Number(t.Value) / 1e6, 2)}M` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted small">최근 내부자 거래 기록이 없어요.</p>
      )}

      <h3 className="sub">상위 기관 보유자</h3>
      {data.institutional_holders.length ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>기관</th>
                <th>지분율</th>
                <th>보유 주식</th>
                <th>직전 대비</th>
                <th>보고일</th>
              </tr>
            </thead>
            <tbody>
              {data.institutional_holders.map((h, i) => (
                <tr key={i}>
                  <td>{String(h.Holder ?? "")}</td>
                  <td>{h.pctHeld != null ? `${num(Number(h.pctHeld) * 100, 2)}%` : "–"}</td>
                  <td>{h.Shares != null ? num(Number(h.Shares), 0) : "–"}</td>
                  <td>{h.pctChange != null ? <Change value={Number(h.pctChange) * 100} digits={1} /> : "–"}</td>
                  <td>{String(h["Date Reported"] ?? "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted small">기관 보유 데이터가 없어요.</p>
      )}
    </div>
  );
}

function News({ symbol }: { symbol: string }) {
  const { data, error, loading } = useApi<{ articles: Article[] }>(`/api/stocks/${symbol}/news`);
  if (error) return <ErrorNote message={error} />;
  if (loading || !data) return <Skeleton height={200} />;
  if (!data.articles.length) return <p className="muted small">최근 2주 안의 기사를 찾지 못했어요.</p>;
  return (
    <ul className="list-plain">
      {data.articles.map((a) => (
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
  );
}

function Filings({ symbol }: { symbol: string }) {
  const { data, error, loading } = useApi<{ filings: Filing[] }>(`/api/stocks/${symbol}/filings`);
  const [onlyMain, setOnlyMain] = useState(false);
  if (error) return <ErrorNote message={error} />;
  if (loading || !data) return <Skeleton height={200} />;
  const rows = onlyMain ? data.filings.filter((f) => ["10-K", "10-Q", "8-K"].includes(f.form)) : data.filings;
  return (
    <>
      <label className="small muted check">
        <input type="checkbox" checked={onlyMain} onChange={(e) => setOnlyMain(e.target.checked)} /> 10-K · 10-Q · 8-K만 보기
      </label>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>날짜</th>
              <th className="left">서류</th>
              <th className="left">설명</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.url}>
                <td>{f.date}</td>
                <td className="left">
                  <a href={f.url} target="_blank" rel="noreferrer" className="ticker">
                    {f.form}
                  </a>{" "}
                  <span className="muted">{f.label}</span>
                </td>
                <td className="left muted">{f.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>
        출처: SEC EDGAR
      </p>
    </>
  );
}

export default function StockPage() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw).toUpperCase();
  const detail = useApi<StockDetail>(`/api/stocks/${symbol}`);
  const catalog = useApi<Catalog>("/api/screener/metrics");
  const watch = useWatchlist();
  const [tab, setTab] = useState<TabKey>("flow");
  const d = detail.data;
  const watched = watch.has(symbol);

  return (
    <>
      <p className="small">
        <Link href="/screener" className="muted">
          ← 스크리너
        </Link>
      </p>
      <div className="stock-head">
        <div>
          <h1>
            {symbol} <span className="stock-head__name">{d?.name}</span>
          </h1>
          {d ? (
            <p className="muted small">
              {[d.sector_label, d.industry].filter(Boolean).join(" · ")}
              {d.employees ? ` · 직원 ${d.employees.toLocaleString()}명` : ""}
            </p>
          ) : null}
        </div>
        <div className="stock-head__price">
          {d ? (
            <>
              <strong>{price(d.price, d.currency)}</strong>
              <Change value={d.change_pct} />
            </>
          ) : null}
          <button
            type="button"
            className={`btn ${watched ? "" : "btn--primary"}`}
            onClick={() => (watched ? watch.remove(symbol) : watch.add({ symbol, name: d?.name, priceAtAdd: d?.price }))}
          >
            {watched ? "★ 관심종목" : "☆ 관심종목에 추가"}
          </button>
        </div>
      </div>

      {detail.error ? <ErrorNote message={detail.error} onRetry={detail.reload} /> : null}

      <div className="grid stock-grid">
        {d && catalog.data ? (
          <AtAGlance
            detail={d}
            catalog={catalog.data}
            onReadFilings={() => {
              setTab("filings");
              document.getElementById("details-tabs")?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          />
        ) : null}
        <PriceChart symbol={symbol} />
        {d?.summary ? (
          <details className="panel summary">
            <summary>회사 소개 (영문)</summary>
            <p>{d.summary}</p>
            {d.website ? (
              <a href={d.website} target="_blank" rel="noreferrer" className="small">
                {d.website}
              </a>
            ) : null}
          </details>
        ) : null}
        <ValuationHistory symbol={symbol} />
        {d && catalog.data ? <MetricCards detail={d} catalog={catalog.data} /> : detail.loading ? <Skeleton height={300} /> : null}

        <section className="panel" id="details-tabs" aria-label="수급, 뉴스, 공시">
          <div className="panel__head">
            <Tabs
              label="세부 정보"
              value={tab}
              onChange={setTab}
              options={[
                { value: "flow", label: "수급" },
                { value: "news", label: "뉴스" },
                { value: "filings", label: "공시" },
              ]}
            />
          </div>
          <div className="panel__body">
            {tab === "flow" ? <Flow symbol={symbol} /> : null}
            {tab === "news" ? <News symbol={symbol} /> : null}
            {tab === "filings" ? <Filings symbol={symbol} /> : null}
          </div>
        </section>
      </div>
    </>
  );
}
