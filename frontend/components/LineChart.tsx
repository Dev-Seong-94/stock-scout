"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { num } from "@/lib/format";

export type ChartSeries = {
  label: string;
  values: (number | null)[];
  color: string;
  width?: number;
  dashed?: boolean;
};

type Props = {
  dates: string[];
  series: ChartSeries[];
  height?: number;
  unit?: string;
  digits?: number;
  /** Draw a reference line, e.g. 0 for spreads or 2 for the Fed's inflation target. */
  reference?: { value: number; label: string };
  ariaLabel: string;
};

export const PAD = { top: 12, right: 52, bottom: 24, left: 8 };

export function niceTicks(min: number, max: number, count = 4): number[] {
  const span = max - min || Math.abs(max) || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const start = Math.ceil(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 1e-6; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

export default function LineChart({ dates, series, height = 220, unit = "", digits = 2, reference, ariaLabel }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const [width, setWidth] = useState(640);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const el = svgRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [dates.length > 0]);

  const { min, max } = useMemo(() => {
    const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
    if (reference) all.push(reference.value);
    let lo = Math.min(...all);
    let hi = Math.max(...all);
    if (!Number.isFinite(lo)) return { min: 0, max: 1 };
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
    lo -= pad;
    hi += pad;
    return { min: lo, max: hi };
  }, [series, reference]);

  const n = dates.length;
  const innerW = width - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (n <= 1 ? 0 : (i / (n - 1)) * innerW);
  const y = (v: number) => PAD.top + (1 - (v - min) / (max - min)) * innerH;

  const paths = series.map((s) => {
    let d = "";
    let pen = false;
    s.values.forEach((v, i) => {
      if (v === null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  });

  const ticks = niceTicks(min, max);
  const labelIdx = n > 1 ? [0, Math.floor((n - 1) / 2), n - 1] : [0];

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const rel = (e.clientX - rect.left - PAD.left) / innerW;
    setHover(Math.max(0, Math.min(n - 1, Math.round(rel * (n - 1)))));
  };

  const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${num(v, digits)}${unit}`);

  if (!n) return null;

  return (
    <figure className="chart">
      <svg
        ref={svgRef}
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        style={{ display: "block", touchAction: "pan-y" }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth="1" />
            <text x={width - PAD.right + 6} y={y(t)} dy="0.32em" fontSize="11" fill="var(--faint)">
              {num(t, Math.abs(t) >= 100 ? 0 : t % 1 === 0 ? 0 : 1)}
            </text>
          </g>
        ))}
        {reference ? (
          <g>
            <line
              x1={PAD.left}
              x2={width - PAD.right}
              y1={y(reference.value)}
              y2={y(reference.value)}
              stroke="var(--muted)"
              strokeDasharray="4 3"
            />
            <text x={PAD.left + 4} y={y(reference.value) - 4} fontSize="11" fill="var(--muted)">
              {reference.label}
            </text>
          </g>
        ) : null}
        {series.map((s, i) => (
          <path
            key={s.label}
            d={paths[i]}
            fill="none"
            stroke={s.color}
            strokeWidth={s.width ?? 1.75}
            strokeDasharray={s.dashed ? "5 4" : undefined}
            strokeLinejoin="round"
          />
        ))}
        {labelIdx.map((i, k) => (
          <text
            key={i}
            x={x(i)}
            y={height - 6}
            fontSize="11"
            fill="var(--faint)"
            textAnchor={k === 0 ? "start" : k === labelIdx.length - 1 ? "end" : "middle"}
          >
            {dates[i]}
          </text>
        ))}
        {hover !== null ? (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + innerH} stroke="var(--muted)" strokeWidth="1" />
            {series.map((s) =>
              s.values[hover] !== null && s.values[hover] !== undefined ? (
                <circle key={s.label} cx={x(hover)} cy={y(s.values[hover] as number)} r="3.5" fill={s.color} />
              ) : null,
            )}
          </g>
        ) : null}
      </svg>
      <figcaption className="chart__legend small">
        <span className="muted">{hover !== null ? dates[hover] : dates[n - 1]}</span>
        {series.map((s) => (
          <span key={s.label}>
            <i style={{ background: s.color }} aria-hidden="true" />
            {s.label} <b>{fmt(s.values[hover ?? n - 1])}</b>
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
