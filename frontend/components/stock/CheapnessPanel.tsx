"use client";

import { ErrorNote, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { metricValue, sectorRank } from "@/lib/format";
import type { Cheapness, CheapnessStatus } from "@/lib/types";

const usd = (v: number) => `$${v.toLocaleString("en-US", { maximumFractionDigits: v >= 100 ? 0 : 2 })}`;
const pct = (v: number) => `${Math.round(v * 1000) / 10}%`;

function Mark({ status, met, unmet }: { status: CheapnessStatus; met: string; unmet: string }) {
  if (status === "na") return <span className="cheap__mark">확인 불가</span>;
  return <span className={`cheap__mark ${status === "met" ? "is-met" : ""}`}>{status === "met" ? met : unmet}</span>;
}

/** "싼가?": the same three conditions the screener counts. Facts and a direction, never a verdict. */
export function CheapnessPanel({ symbol }: { symbol: string }) {
  const { data, error, loading, reload } = useApi<Cheapness>(`/api/stocks/${symbol}/cheapness`);
  const built = data?.built_at ? new Date(data.built_at) : null;
  const a = data?.assumptions;
  const cash = data?.conditions?.find((c) => c.key === "cash");
  return (
    <section className="panel" id="stock-cheap" aria-labelledby="cheap-title">
      <div className="panel__head">
        <h2 id="cheap-title">싼가?</h2>
        {built ? (
          <span className="small muted">
            스크리너 데이터 {built.getMonth() + 1}/{built.getDate()} 기준
          </span>
        ) : null}
      </div>
      <div className="panel__body">
        {error ? <ErrorNote message={error} onRetry={reload} /> : null}
        {loading && !data ? <Skeleton height={120} /> : null}
        {data && !data.in_snapshot ? <p className="small muted">이 종목은 스크리너 데이터에 없어서 비교할 수 없어요.</p> : null}
        {data?.conditions ? (
          <>
            <dl className="cheap__rows">
              {data.conditions.map((c) => (
                <div key={c.key} className="cheap__row">
                  <dt>{c.label}</dt>
                  <dd className="cheap__facts">
                    {c.status === "na" ? <span className="muted">{c.reason}</span> : null}
                    {c.status !== "na" && c.key === "sector" ? (
                      <>
                        PER {metricValue(c.pe, "x")} / {data.sector_label} 중앙값 {metricValue(data.sector_median_pe ?? null, "x")}
                        {c.percentile != null ? ` / ${sectorRank(c.percentile)}` : ""}
                      </>
                    ) : null}
                    {c.status !== "na" && c.key === "own_past" ? (
                      <>
                        PER {metricValue(c.current, "x")} / {c.since?.slice(0, 4)}년 이후 중앙값 {metricValue(c.median, "x")}{" "}
                        <span className="small muted">직전 회계연도 기준</span>
                      </>
                    ) : null}
                    {c.status !== "na" && c.key === "cash" && c.values && c.price != null ? (
                      <>
                        계산값 {usd(c.values.low)} ~ {usd(c.values.base)} ~ {usd(c.values.high)} / 스냅샷 주가 {usd(c.price)}
                      </>
                    ) : null}
                  </dd>
                  <dd style={{ margin: 0 }}>
                    {c.key === "sector" ? <Mark status={c.status} met="낮은 쪽" unmet="하위 40% 밖" /> : null}
                    {c.key === "own_past" ? <Mark status={c.status} met="낮은 쪽" unmet="중앙값 이상" /> : null}
                    {c.key === "cash" ? <Mark status={c.status} met="기본 계산값보다 낮음" unmet="기본 계산값 이상" /> : null}
                  </dd>
                </div>
              ))}
            </dl>
            {cash?.status !== "na" && a ? (
              <p className="cheap__note small muted">
                현금 기준 계산값은 <b>목표가가 아니에요.</b> 최근 12개월 잉여현금흐름이 {a.years}년간 연 {pct(a.growth.low)}·{pct(a.growth.base)}·
                {pct(a.growth.high)} 자란다고 가정하고, 할인율 {pct(a.discount)}, 이후 연 {pct(a.terminal)} 성장을 넣은 값이에요. 모든 회사에 같은 가정을 쓰고,
                가정을 바꾸면 크게 달라져요. 최근 1년 현금흐름이 평소와 다른 회사는 왜곡돼요.
              </p>
            ) : null}
            <p className="cheap__note small muted">싼 데는 이유가 있을 수 있어요. 낮은 쪽이라는 표시는 판단이 아니라 비교 결과예요.</p>
          </>
        ) : null}
      </div>
    </section>
  );
}
