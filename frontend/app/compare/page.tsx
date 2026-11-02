"use client";

import Link from "next/link";
import { Fragment } from "react";

import { CriteriaSummary } from "@/components/MyCriteria";
import { ErrorNote, InfoTip, Skeleton, WatchStar } from "@/components/ui";
import { useApi } from "@/lib/api";
import { focusMetrics } from "@/lib/criteria";
import { direction, metricCell, metricValue, price, sectorRank } from "@/lib/format";
import { COMPARE_MAX, useCompare, useProfile, useWatchlist } from "@/lib/storage";
import { SECTOR_SUFFIX } from "@/lib/types";
import type { Catalog, CompareResult, Metric, ScreenRow } from "@/lib/types";

const SIGNED = new Set(["ret_1m", "ret_3m", "ret_6m", "ret_1y", "dist_sma50", "dist_sma200", "from_52w_high", "share_change_1y", "gross_margin_change"]);

function usableValue(row: ScreenRow, m: Metric): number | null {
  const v = row[m.key];
  if (typeof v !== "number") return null;
  return m.positive_only && v <= 0 ? null : v;
}

/** The stock that sits on the usually-favourable side, when there is a clear one. */
function favoured(rows: ScreenRow[], m: Metric): string | null {
  if (!m.prefer) return null;
  const vals = rows.map((r) => [r.symbol, usableValue(r, m)] as const).filter((x): x is readonly [string, number] => x[1] !== null);
  if (vals.length < 2) return null;
  const sorted = [...vals].sort((a, b) => (m.prefer === "high" ? b[1] - a[1] : a[1] - b[1]));
  return sorted[0][1] === sorted[1][1] ? null : sorted[0][0];
}

function MetricRow({ m, rows, medians }: { m: Metric; rows: ScreenRow[]; medians: CompareResult["medians"] }) {
  const best = favoured(rows, m);
  return (
    <tr>
      <th scope="row" className="left">
        <span className="compare__metric">
          {m.label}
          <InfoTip metric={m} />
        </span>
        {m.prefer ? <span className="compare__prefer small muted">{m.prefer === "high" ? "보통 높을수록 유리" : "보통 낮을수록 유리"}</span> : null}
      </th>
      {rows.map((r) => {
        const v = r[m.key] as number | null;
        const pct = r[m.key + SECTOR_SUFFIX] as number | null;
        const med = r.sector ? medians[r.sector]?.[m.key] : undefined;
        return (
          <td key={r.symbol} className={best === r.symbol ? "is-favoured" : undefined}>
            <span className={SIGNED.has(m.key) ? direction(v) : undefined}>{metricCell(v, m)}</span>
            <span className="compare__ctx small muted">
              {sectorRank(pct)}
              {med !== undefined ? `${pct != null ? " · " : ""}섹터 중앙 ${metricValue(med, m.unit)}` : ""}
            </span>
          </td>
        );
      })}
    </tr>
  );
}

export default function ComparePage() {
  const compare = useCompare();
  const watch = useWatchlist();
  const [profile] = useProfile();
  const catalogReq = useApi<Catalog>("/api/screener/metrics");
  const symbols = compare.symbols.join(",");
  const req = useApi<CompareResult>(symbols ? `/api/screener/compare?symbols=${encodeURIComponent(symbols)}` : null);
  const catalog = catalogReq.data;
  const rows = req.data?.rows ?? [];
  const sectorLabel = new Map((catalog?.sectors ?? []).map((s) => [s.key, s.label]));
  const metricsByKey = new Map((catalog?.metrics ?? []).map((m) => [m.key, m]));
  const focus = profile ? focusMetrics(profile).map((k) => metricsByKey.get(k)).filter((m): m is Metric => !!m) : [];
  const watchSymbols = watch.items.map((i) => i.symbol);

  return (
    <>
      <div className="page-head">
        <h1>나란히 비교</h1>
        <p className="small muted">최대 {COMPARE_MAX}개 · 스크리너 데이터 기준</p>
      </div>

      {!compare.symbols.length ? (
        <div className="note">
          <p>
            아직 비교함이 비어 있어요. 스크리너 결과에서 왼쪽 <b>비교</b> 칸을 체크해 2~{COMPARE_MAX}개를 담아 주세요.
          </p>
          {watchSymbols.length >= 2 ? (
            <p style={{ marginTop: 8 }}>
              <button type="button" className="btn" onClick={() => compare.set(watchSymbols.slice(0, COMPARE_MAX))}>
                관심종목 {Math.min(COMPARE_MAX, watchSymbols.length)}개로 비교하기
              </button>
            </p>
          ) : null}
          <p style={{ marginTop: 8 }}>
            <Link href="/screener">스크리너로 가기</Link>
          </p>
        </div>
      ) : null}

      {catalogReq.error ? <ErrorNote message={catalogReq.error} onRetry={catalogReq.reload} /> : null}
      {req.error ? <ErrorNote message={req.error} onRetry={req.reload} /> : null}
      {compare.symbols.length && (req.loading || !catalog) && !rows.length ? <Skeleton height={400} /> : null}
      {req.data?.missing?.length ? <p className="note small">{req.data.missing.join(", ")}은(는) 스크리너 데이터에 없어서 뺐어요.</p> : null}

      {catalog && rows.length ? (
        <>
          <CriteriaSummary />
          <p className="small muted compare__legend">
            <span className="compare__swatch" aria-hidden="true" /> 표시는 그 지표를 보통 유리하게 읽는 쪽(덜 비싸다, 더 잘 번다, 빚이 적다)에 있는 종목이에요. 정답이 아니라 읽는 방향의
            표시예요. 업종이 다르면 숫자를 바로 비교하기 어려우니 아래 &apos;섹터 상위/하위&apos;를 같이 보세요.
          </p>
          <div className="panel table-wrap">
            <table className="table compare">
              <thead>
                <tr>
                  <th scope="col" className="left">
                    <span className="sr-only">지표</span>
                  </th>
                  {rows.map((r) => (
                    <th key={r.symbol} scope="col" className="compare__head">
                      <span className="compare__title">
                        <Link className="ticker" href={`/stocks/${r.symbol}`}>
                          {r.symbol}
                        </Link>
                        <WatchStar
                          symbol={r.symbol}
                          active={watch.has(r.symbol)}
                          onToggle={() =>
                            watch.has(r.symbol) ? watch.remove(r.symbol) : watch.add({ symbol: r.symbol, name: r.name, priceAtAdd: r.price as number | null })
                          }
                        />
                        <button type="button" className="btn btn--ghost small" aria-label={`${r.symbol} 비교에서 빼기`} onClick={() => compare.toggle(r.symbol)}>
                          ×
                        </button>
                      </span>
                      <span className="small muted">{r.name}</span>
                      <span className="small muted">
                        {sectorLabel.get(r.sector ?? "") ?? r.sector ?? "–"} · {price(r.price as number | null)}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {focus.length ? (
                  <>
                    <tr className="compare__group">
                      <th colSpan={rows.length + 1} className="left">
                        내 기준으로 먼저 볼 지표
                      </th>
                    </tr>
                    {focus.map((m) => (
                      <MetricRow key={`mine-${m.key}`} m={m} rows={rows} medians={req.data!.medians} />
                    ))}
                  </>
                ) : null}
                {catalog.groups.map((g) => (
                  <Fragment key={g.key}>
                    <tr className="compare__group">
                      <th colSpan={rows.length + 1} className="left">
                        {g.label}
                      </th>
                    </tr>
                    {catalog.metrics
                      .filter((m) => m.group === g.key)
                      .map((m) => (
                        <MetricRow key={m.key} m={m} rows={rows} medians={req.data!.medians} />
                      ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <p className="disclaimer">
            숫자가 비슷하면 회사가 하는 일, 최근 공시, 뉴스에서 차이가 나요. 마음이 가는 종목은 ☆로 관심종목에 담고, 관심종목 화면의 확인 목록을 채워 보세요.
          </p>
        </>
      ) : null}
    </>
  );
}
