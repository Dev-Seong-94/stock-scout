"use client";

import Link from "next/link";

import { COMPARE_MAX, useCompare } from "@/lib/storage";

/** Sticky bar while stocks are picked for the side-by-side view. */
export function CompareBar() {
  const compare = useCompare();
  if (!compare.symbols.length) return null;
  return (
    <div className="compare-bar" role="region" aria-label="비교함">
      <span className="small">
        비교함 <b>{compare.symbols.length}</b>/{COMPARE_MAX}
      </span>
      <span className="compare-bar__list small">
        {compare.symbols.map((s) => (
          <span key={s} className="chip">
            {s}
            <button type="button" aria-label={`${s} 비교함에서 빼기`} onClick={() => compare.toggle(s)}>
              ×
            </button>
          </span>
        ))}
      </span>
      <button type="button" className="btn btn--ghost small" onClick={() => compare.set([])}>
        비우기
      </button>
      {compare.symbols.length < 2 ? (
        <span className="small muted">하나 더 담으면 비교할 수 있어요</span>
      ) : (
        <Link className="btn btn--primary" href="/compare">
          나란히 비교하기
        </Link>
      )}
    </div>
  );
}
