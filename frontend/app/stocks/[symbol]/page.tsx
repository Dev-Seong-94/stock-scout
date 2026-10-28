"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import LineChart from "@/components/LineChart";
import { Change, ErrorNote, InfoTip, Skeleton, Tabs } from "@/components/ui";
import { useApi } from "@/lib/api";
import { metricValue, num, price, relativeTime } from "@/lib/format";
import { useWatchlist } from "@/lib/storage";
import type { Article, Catalog, Filing, Ownership, PriceHistory, StockDetail } from "@/lib/types";

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
            회색 숫자는 같은 섹터({detail.sector_label}) {detail.peer_count}개 종목의 중앙값이에요.
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
                return (
                  <div key={m.key} className="metric-card">
                    <div className="metric-card__label">
                      <span>{m.label}</span>
                      <InfoTip metric={m} />
                    </div>
                    <p className="metric-card__value">{metricValue(v, m.unit)}</p>
                    {med !== undefined ? <p className="metric-card__median">섹터 {metricValue(med, m.unit)}</p> : null}
                  </div>
                );
              })}
          </div>
        </div>
      ))}
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
        {d && catalog.data ? <MetricCards detail={d} catalog={catalog.data} /> : detail.loading ? <Skeleton height={300} /> : null}

        <section className="panel" aria-label="수급, 뉴스, 공시">
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
