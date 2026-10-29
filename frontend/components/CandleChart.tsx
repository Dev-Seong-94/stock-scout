"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { niceTicks, PAD, type ChartSeries } from "@/components/LineChart";
import { num, signed } from "@/lib/format";

type Props = {
  dates: string[];
  open: (number | null)[];
  high: (number | null)[];
  low: (number | null)[];
  close: (number | null)[];
  volume: (number | null)[];
  /** Moving averages drawn over the candles. */
  overlays: ChartSeries[];
  height?: number;
  digits?: number;
  ariaLabel: string;
};

const VOLUME_H = 56; // volume bars under the price pane
const GAP = 8;

function compact(v: number) {
  if (v >= 1e9) return `${num(v / 1e9, 1)}B`;
  if (v >= 1e6) return `${num(v / 1e6, 1)}M`;
  if (v >= 1e3) return `${num(v / 1e3, 0)}K`;
  return num(v, 0);
}

/** Candlesticks (up = close above open, coloured with the up/down setting) plus volume. */
export default function CandleChart({ dates, open, high, low, close, volume, overlays, height = 320, digits = 2, ariaLabel }: Props) {
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
    const all = [...high, ...low, ...overlays.flatMap((s) => s.values)].filter((v): v is number => v !== null);
    let lo = Math.min(...all);
    let hi = Math.max(...all);
    if (!Number.isFinite(lo)) return { min: 0, max: 1 };
    const pad = (hi - lo) * 0.06 || Math.abs(hi) * 0.05 || 1;
    lo -= pad;
    hi += pad;
    return { min: lo, max: hi };
  }, [high, low, overlays]);

  const n = dates.length;
  const innerW = width - PAD.left - PAD.right;
  const priceH = height - PAD.top - PAD.bottom - VOLUME_H - GAP;
  const volTop = PAD.top + priceH + GAP;
  const slot = innerW / Math.max(1, n);
  const bodyW = Math.max(1, Math.min(14, slot * 0.7));
  const x = (i: number) => PAD.left + slot * (i + 0.5);
  const y = (v: number) => PAD.top + (1 - (v - min) / (max - min)) * priceH;
  const maxVol = Math.max(1, ...volume.filter((v): v is number => v !== null));

  const lines = overlays.map((s) => {
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

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.floor((e.clientX - rect.left - PAD.left) / slot);
    setHover(Math.max(0, Math.min(n - 1, i)));
  };

  if (!n) return null;

  const ticks = niceTicks(min, max);
  const labelIdx = n > 1 ? [0, Math.floor((n - 1) / 2), n - 1] : [0];
  const at = hover ?? n - 1;
  const prevClose = at > 0 ? close[at - 1] : null;
  const dayChange = prevClose && close[at] !== null ? ((close[at]! / prevClose) - 1) * 100 : null;
  const p = (v: number | null) => (v === null ? "–" : num(v, digits));

  return (
    <figure className="chart">
      <figcaption className="chart__ohlc small">
        <span className="muted">{dates[at]}</span>
        <span>
          시가 <b>{p(open[at])}</b>
        </span>
        <span>
          고가 <b>{p(high[at])}</b>
        </span>
        <span>
          저가 <b>{p(low[at])}</b>
        </span>
        <span>
          종가 <b>{p(close[at])}</b>{" "}
          {dayChange !== null ? <span className={dayChange >= 0 ? "up" : "down"}>{signed(dayChange, 2, "%")}</span> : null}
        </span>
        <span>
          거래량 <b>{volume[at] !== null ? compact(volume[at]!) : "–"}</b>
        </span>
      </figcaption>
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
        <line x1={PAD.left} x2={width - PAD.right} y1={volTop + VOLUME_H} y2={volTop + VOLUME_H} stroke="var(--line)" />

        {dates.map((_, i) => {
          const o = open[i];
          const c = close[i];
          const h = high[i];
          const l = low[i];
          const v = volume[i];
          if (o === null || c === null || h === null || l === null) return null;
          const color = c >= o ? "var(--up)" : "var(--down)";
          const top = y(Math.max(o, c));
          const bodyH = Math.max(1, Math.abs(y(o) - y(c)));
          return (
            <g key={i}>
              <line x1={x(i)} x2={x(i)} y1={y(h)} y2={y(l)} stroke={color} strokeWidth="1" />
              <rect x={x(i) - bodyW / 2} y={top} width={bodyW} height={bodyH} fill={color} />
              {v !== null ? (
                <rect
                  x={x(i) - bodyW / 2}
                  y={volTop + VOLUME_H - (v / maxVol) * VOLUME_H}
                  width={bodyW}
                  height={(v / maxVol) * VOLUME_H}
                  fill={color}
                  opacity="0.35"
                />
              ) : null}
            </g>
          );
        })}

        {overlays.map((s, i) => (
          <path key={s.label} d={lines[i]} fill="none" stroke={s.color} strokeWidth={s.width ?? 1.5} strokeDasharray={s.dashed ? "5 4" : undefined} />
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
          <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={volTop + VOLUME_H} stroke="var(--muted)" strokeWidth="1" strokeDasharray="3 3" />
        ) : null}
      </svg>
      <figcaption className="chart__legend small">
        {overlays.map((s) => (
          <span key={s.label}>
            <i style={{ background: s.color }} aria-hidden="true" />
            {s.label} <b>{p(s.values[at])}</b>
          </span>
        ))}
        <span className="muted">아래 막대는 거래량</span>
      </figcaption>
    </figure>
  );
}
