"use client";

import { Change, ErrorNote, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { metricValue, signed } from "@/lib/format";
import type { Decline, DeclineWindow } from "@/lib/types";

const WINDOWS: DeclineWindow[] = ["1m", "3m", "6m", "1y"];

function Row({ label, values }: { label: string; values: Record<DeclineWindow, number | null> }) {
  return (
    <tr>
      <td>{label}</td>
      {WINDOWS.map((w) => (
        <td key={w}>
          <Change value={values[w]} digits={1} />
        </td>
      ))}
    </tr>
  );
}

function quarterLabel(date: string) {
  return `${date.slice(0, 4)}년 ${Number(date.slice(5, 7))}월 말 분기`;
}

/** "왜 떨어졌나?": compares, never names a cause. Fixed sentences come from the backend. */
export function DeclinePanel({ symbol, onReadFilings }: { symbol: string; onReadFilings: () => void }) {
  const { data, error, loading, reload } = useApi<Decline>(`/api/stocks/${symbol}/decline`);
  const t = data?.trend;
  return (
    <section className="panel" id="stock-decline" aria-labelledby="decline-title">
      <div className="panel__head">
        <h2 id="decline-title">왜 떨어졌나?</h2>
        <span className="small muted">원인을 단정하지 않고 숫자만 나란히 놓아요.</span>
      </div>
      <div className="panel__body">
        {error ? <ErrorNote message={error} onRetry={reload} /> : null}
        {loading && !data ? <Skeleton height={160} /> : null}
        {data ? (
          <>
            <div className="table-wrap">
              <table className="table decline__table">
                <caption className="sr-only">이 종목, 섹터, S&amp;P 500의 기간별 수익률</caption>
                <thead>
                  <tr>
                    <th scope="col">수익률</th>
                    {WINDOWS.map((w) => (
                      <th key={w} scope="col">
                        {data.windows[w]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <Row label={symbol} values={data.stock} />
                  <Row label={data.etf ? `${data.sector_label} (${data.etf})` : "섹터"} values={data.sector} />
                  <Row label="S&P 500 (SPY)" values={data.market} />
                </tbody>
              </table>
            </div>
            {data.return_facts.length ? (
              <ul className="decline__facts small">
                {data.return_facts.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            ) : null}

            <div className="decline__trend">
              <h3>회사 실적{t ? ` · ${quarterLabel(t.quarter)}, 전년 같은 분기와 비교` : ""}</h3>
              {t ? (
                <dl className="decline__stats small">
                  <div>
                    <dt>매출</dt>
                    <dd>{t.revenue_change != null ? signed(t.revenue_change, 1, "%") : "데이터 없음"}</dd>
                  </div>
                  <div>
                    <dt>영업이익률</dt>
                    <dd>
                      {t.operating_margin != null ? metricValue(t.operating_margin, "%") : "데이터 없음"}
                      {t.operating_margin_year_ago != null ? ` (전년 ${metricValue(t.operating_margin_year_ago, "%")})` : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>희석 주식 수</dt>
                    <dd>{t.shares_change != null ? signed(t.shares_change, 1, "%") : "데이터 없음"}</dd>
                  </div>
                </dl>
              ) : (
                <p className="small muted">분기 실적 데이터를 찾지 못했어요.</p>
              )}
              {data.earnings_facts.length ? (
                <ul className="decline__facts small">
                  {data.earnings_facts.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              ) : null}
              <p className="glance__next small">
                숫자로는 이유까지 알 수 없어요. 최근 분기 보고서(10-Q)나 실적 발표(8-K)에서 회사의 설명을 확인해 보세요.{" "}
                <button type="button" className="btn btn--ghost small" onClick={onReadFilings}>
                  공시 보기
                </button>
              </p>
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
