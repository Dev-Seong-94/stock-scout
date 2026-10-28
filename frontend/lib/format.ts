const nf = (digits: number) =>
  new Intl.NumberFormat("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function num(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  return nf(digits).format(v);
}

export function signed(v: number | null | undefined, digits = 2, suffix = ""): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const s = nf(digits).format(Math.abs(v));
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${s}${suffix}`;
}

/** Format a metric value according to its unit from the catalog. */
export function metricValue(v: number | string | null | undefined, unit: string): string {
  if (v === null || v === undefined || v === "") return "–";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return String(v);
  switch (unit) {
    case "%":
      return `${num(n, 1)}%`;
    case "x":
      return `${num(n, n >= 100 ? 0 : 1)}배`;
    case "$B":
      return n >= 1000 ? `$${num(n / 1000, 2)}T` : `$${num(n, n >= 100 ? 0 : 1)}B`;
    case "$M":
      return n >= 1000 ? `$${num(n / 1000, 1)}B` : `$${num(n, 0)}M`;
    default:
      return num(n, n >= 100 ? 0 : 2);
  }
}

export function unitSuffix(unit: string): string {
  return { "%": "%", x: "배", $B: "B$", $M: "M$" }[unit] ?? "";
}

export function price(v: number | null | undefined, currency = "USD"): string {
  if (v === null || v === undefined) return "–";
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(v);
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (Number.isNaN(diff)) return "";
  if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))}분 전`;
  if (diff < 86400) return `${Math.round(diff / 3600)}시간 전`;
  if (diff < 86400 * 7) return `${Math.round(diff / 86400)}일 전`;
  return shortDate(iso);
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

export function dayLabel(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return `${m}월 ${d}일 (${WEEKDAYS[date.getDay()]})`;
}

/** "up" / "down" / "" for colouring changes. */
export function direction(v: number | null | undefined): "up" | "down" | "" {
  if (!v) return "";
  return v > 0 ? "up" : "down";
}
