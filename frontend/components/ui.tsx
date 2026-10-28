"use client";

import { useEffect, useId, useRef, useState } from "react";

import { direction, signed } from "@/lib/format";
import type { Metric } from "@/lib/types";

export function Change({
  value,
  digits = 2,
  suffix = "%",
  className = "",
}: {
  value: number | null | undefined;
  digits?: number;
  suffix?: string;
  className?: string;
}) {
  return <span className={`${direction(value)} ${className}`.trim()}>{signed(value, digits, suffix)}</span>;
}

export function Sparkline({ values, width = 120, height = 32 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const d = values
    .map((v, i) => `${i ? "L" : "M"}${((i / (values.length - 1)) * width).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`)
    .join(" ");
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" style={{ display: "block" }}>
      <path d={d} fill="none" stroke={rising ? "var(--up)" : "var(--down)"} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

/** Explanation popover for a metric: what it measures, how to read it, pitfalls. */
export function InfoTip({ metric, extra }: { metric: Pick<Metric, "label" | "description" | "reading" | "caveat">; extra?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const ref = useRef<HTMLSpanElement>(null);
  const id = useId();

  // Fixed positioning so the popover is never clipped by a scrolling panel.
  const place = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const width = Math.min(320, window.innerWidth * 0.8);
    const left = Math.max(8, Math.min(r.left - 8, window.innerWidth - width - 8));
    setPos({ top: r.bottom + 6, left });
  };

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const dismiss = () => setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [open]);

  return (
    <span className="info" ref={ref}>
      <button
        type="button"
        className="info__btn"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`${metric.label} 설명`}
        onClick={(e) => {
          e.stopPropagation();
          if (!open) place();
          setOpen((o) => !o);
        }}
      >
        ?
      </button>
      {open ? (
        <dl className="info__pop" id={id} role="note" style={pos ?? undefined}>
          <dt>무엇을 재나요</dt>
          <dd>{metric.description}</dd>
          {metric.reading ? (
            <>
              <dt>어떻게 읽나요</dt>
              <dd>{metric.reading}</dd>
            </>
          ) : null}
          {metric.caveat ? (
            <>
              <dt>주의할 점</dt>
              <dd>{metric.caveat}</dd>
            </>
          ) : null}
          {extra}
        </dl>
      ) : null}
    </span>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="note note--error" role="alert">
      {message}{" "}
      {onRetry ? (
        <button type="button" className="btn btn--ghost small" onClick={onRetry}>
          다시 시도
        </button>
      ) : null}
    </div>
  );
}

export function Skeleton({ height = 16, width = "100%" }: { height?: number; width?: number | string }) {
  return <div className="skeleton" style={{ height, width }} aria-hidden="true" />;
}

export function Tabs<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="tabs" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function WatchStar({ active, onToggle, symbol }: { active: boolean; onToggle: () => void; symbol: string }) {
  return (
    <button
      type="button"
      className="star"
      aria-pressed={active}
      aria-label={active ? `${symbol} 관심종목에서 빼기` : `${symbol} 관심종목에 추가`}
      title={active ? "관심종목에서 빼기" : "관심종목에 추가"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
    >
      {active ? "★" : "☆"}
    </button>
  );
}
