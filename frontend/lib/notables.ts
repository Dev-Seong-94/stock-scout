// "눈에 띄는 점" on the stock page: fixed rules that describe, never judge.
// Each line states a fact and, where useful, what to check next.

import { metricValue, sectorRank } from "@/lib/format";
import type { Metric, StockDetail } from "@/lib/types";

export type Notable = { text: string; watch?: boolean };

const EXTREME = 10; // top or bottom 10% of the sector
const MAX_SECTOR_LINES = 4;
// Price moves get their own lines below; sector rank of a 1-month return says little.
const SKIP_SECTOR = new Set(["ret_1m", "ret_3m", "ret_6m", "ret_1y", "rsi14", "dist_sma50", "dist_sma200", "from_52w_high", "rel_volume", "price"]);

export function notables(d: StockDetail, metrics: Metric[]): Notable[] {
  const by = new Map(metrics.map((m) => [m.key, m]));
  const v = (key: string) => d.metrics[key] ?? null;
  const fmt = (key: string, value: number) => metricValue(value, by.get(key)?.unit ?? "");
  const out: Notable[] = [];

  // Money-losing companies: how long the cash lasts and whether shareholders are diluted.
  const netMargin = v("net_margin");
  if (netMargin !== null && netMargin < 0) {
    out.push({ text: `최근 12개월은 적자예요 (순이익률 ${fmt("net_margin", netMargin)}). PER 대신 PSR과 현금을 보세요.`, watch: true });
    const runway = v("cash_runway");
    if (runway !== null) {
      out.push({
        text: runway >= 120 ? "지금 현금 소진 속도면 10년 이상 버틸 현금이 있어요." : `지금 현금 소진 속도면 현금이 약 ${Math.round(runway)}개월 버텨요.`,
        watch: runway < 24,
      });
    }
  }
  const shares = v("share_change_1y");
  if (shares !== null && shares >= 5) {
    out.push({ text: `주식 수가 1년 새 ${fmt("share_change_1y", shares)} 늘었어요. 기존 주주 몫이 그만큼 줄어요(희석).`, watch: true });
  } else if (shares !== null && shares <= -3) {
    out.push({ text: `주식 수가 1년 새 ${fmt("share_change_1y", Math.abs(shares))} 줄었어요. 자사주 매입을 하고 있다는 뜻이에요.` });
  }

  // Where it stands out within its sector, most extreme first.
  const ranked = Object.entries(d.sector_percentile ?? {})
    .filter(([key, p]) => by.has(key) && !SKIP_SECTOR.has(key) && (p >= 100 - EXTREME || p <= EXTREME) && v(key) !== null)
    .sort((a, b) => Math.abs(b[1] - 50) - Math.abs(a[1] - 50))
    .slice(0, MAX_SECTOR_LINES);
  for (const [key, p] of ranked) {
    const med = d.sector_median[key];
    const medText = med !== undefined ? `, 섹터 중앙 ${fmt(key, med)}` : "";
    out.push({ text: `${by.get(key)!.label} ${fmt(key, v(key)!)}: ${sectorRank(p)}${medText}` });
  }

  // Price position.
  const fromHigh = v("from_52w_high");
  if (fromHigh !== null && fromHigh <= -30) {
    out.push({ text: `주가가 52주 고점보다 ${fmt("from_52w_high", Math.abs(fromHigh))} 낮아요. 왜 빠졌는지 최근 실적 발표와 뉴스를 먼저 보세요.`, watch: true });
  }
  const rsi = v("rsi14");
  if (rsi !== null && rsi >= 70) out.push({ text: `RSI ${Math.round(rsi)}: 최근 짧은 기간에 많이 올랐어요.` });
  else if (rsi !== null && rsi <= 30) out.push({ text: `RSI ${Math.round(rsi)}: 최근 짧은 기간에 많이 빠졌어요.` });
  const sma200 = v("dist_sma200");
  if (sma200 !== null) {
    out.push({ text: sma200 >= 0 ? `주가가 200일 이동평균보다 ${fmt("dist_sma200", sma200)} 위에 있어요 (장기 상승 흐름).` : `주가가 200일 이동평균보다 ${fmt("dist_sma200", Math.abs(sma200))} 아래에 있어요 (장기 하락 흐름).` });
  }
  return out;
}
