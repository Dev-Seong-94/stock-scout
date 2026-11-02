import { metricValue } from "@/lib/format";
import { SECTOR_SUFFIX } from "@/lib/types";
import type { Metric, Range, ScreenResult } from "@/lib/types";

// Signed price moves get up/down colour; everything else stays neutral.
export const SIGNED = new Set(["ret_1m", "ret_3m", "ret_6m", "ret_1y", "dist_sma50", "dist_sma200", "from_52w_high", "share_change_1y", "gross_margin_change"]);

export const baseKey = (key: string) => (key.endsWith(SECTOR_SUFFIX) ? key.slice(0, -SECTOR_SUFFIX.length) : key);

export function isActive(r: Range | undefined) {
  return !!r && (r[0] !== null || r[1] !== null);
}

// Metrics where the sign carries the meaning (up/down, above/below). "최대 −20"
// reads backwards for them, so conditions are also said in words.
type Words = { subj: string; up: string; down: string; notUp: string; notDown: string; zeroUp: string; zeroDown: string; unit?: string };
const period = (subj: string): Words => ({
  subj,
  up: "오른",
  down: "떨어진",
  notUp: "오르지 않은",
  notDown: "떨어지지 않은",
  zeroUp: `${subj} 오른`,
  zeroDown: `${subj} 떨어진`,
});
const average = (line: string): Words => ({
  subj: `${line}보다`,
  up: "위에 있는",
  down: "아래에 있는",
  notUp: "위로 벗어나지 않은",
  notDown: "아래로 벗어나지 않은",
  zeroUp: `${line} 위에 있는`,
  zeroDown: `${line} 아래에 있는`,
});
const PLAIN: Record<string, Words> = {
  ret_1m: period("한 달간"),
  ret_3m: period("3개월간"),
  ret_6m: period("6개월간"),
  ret_1y: period("1년간"),
  dist_sma50: average("50일선"),
  dist_sma200: average("200일선"),
  from_52w_high: { subj: "고점보다", up: "", down: "빠진", notUp: "", notDown: "빠지지 않은", zeroUp: "고점에 있는", zeroDown: "고점보다 낮은" },
  share_change_1y: {
    subj: "주식 수가 1년간",
    up: "늘어난",
    down: "줄어든",
    notUp: "늘지 않은",
    notDown: "줄지 않은",
    zeroUp: "주식 수가 1년간 늘어난",
    zeroDown: "주식 수가 1년간 줄어든",
  },
  gross_margin_change: {
    subj: "매출총이익률이 1년간",
    up: "오른",
    down: "내린",
    notUp: "오르지 않은",
    notDown: "내리지 않은",
    zeroUp: "매출총이익률이 1년간 오른",
    zeroDown: "매출총이익률이 1년간 내린",
    unit: "%p",
  },
};

/** "고점보다 20% 이상 빠진 종목" for signed metrics; null when no wording fits. */
export function plainRange(key: string, r: Range): string | null {
  const w = PLAIN[key];
  if (!w) return null;
  const u = w.unit ?? "%";
  const n = (v: number) => `${Math.abs(v)}${u}`;
  const [lo, hi] = r;
  let text: string | null = null;
  if (lo !== null && hi !== null) {
    if (hi <= 0 && lo < 0) text = hi === 0 ? `${w.subj} ${n(lo)} 이내로 ${w.down}` : `${w.subj} ${Math.abs(hi)}~${n(lo)} ${w.down}`;
    else if (lo >= 0 && hi > 0 && w.up) text = lo === 0 ? `${w.subj} ${n(hi)} 이내로 ${w.up}` : `${w.subj} ${lo}~${n(hi)} ${w.up}`;
  } else if (lo !== null) {
    text = lo > 0 ? (w.up ? `${w.subj} ${n(lo)} 이상 ${w.up}` : null) : lo === 0 ? w.zeroUp : `${w.subj} ${n(lo)} 넘게 ${w.notDown}`;
  } else if (hi !== null) {
    text = hi < 0 ? `${w.subj} ${n(hi)} 이상 ${w.down}` : hi === 0 ? w.zeroDown : w.notUp ? `${w.subj} ${n(hi)} 넘게 ${w.notUp}` : null;
  }
  return text ? `${text} 종목` : null;
}

export function describeRange(key: string, r: Range, m: Metric) {
  const [lo, hi] = r;
  if (key.endsWith(SECTOR_SUFFIX)) {
    if (lo !== null && hi !== null) return `섹터 내 ${lo}–${hi}%ile`;
    if (lo !== null) return `섹터 상위 ${100 - lo}%`;
    return `섹터 하위 ${hi}%`;
  }
  if (lo !== null && hi !== null) return `${metricValue(lo, m.unit)} ~ ${metricValue(hi, m.unit)}`;
  if (lo !== null) return `${metricValue(lo, m.unit)} 이상`;
  return `${metricValue(hi, m.unit)} 이하`;
}

export function toCsv(rows: ScreenResult["rows"], columns: string[]) {
  const head = ["symbol", "name", "sector", "price", ...columns];
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [head.join(","), ...rows.map((r) => head.map((h) => esc(r[h])).join(","))].join("\n");
}
