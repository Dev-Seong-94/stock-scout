"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLayoutEffect, useRef, useState, type RefObject } from "react";

import { WatchStar } from "@/components/ui";
import { direction, metricCell, price } from "@/lib/format";
import { COMPARE_MAX, useCompare, useWatchlist } from "@/lib/storage";
import type { Metric, ScreenResult } from "@/lib/types";

import { SIGNED } from "./conditions";

export const PAGE_SIZE = 100;

/**
 * True when the table is wider than its box. Only then does the box scroll
 * sideways; otherwise it stays a plain block so the header can stick to the
 * page instead of an inner scroll area.
 */
function useIsWide(boxRef: RefObject<HTMLDivElement | null>, remountKey: unknown) {
  const [wide, setWide] = useState(false);
  useLayoutEffect(() => {
    const box = boxRef.current;
    const table = box?.querySelector("table");
    if (!box || !table) return;
    const measure = () => setWide(table.scrollWidth > box.clientWidth + 1);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(box);
    ro.observe(table);
    return () => ro.disconnect();
  }, [boxRef, remountKey]);
  return wide;
}

/** The results: one row per stock (click opens it), sortable metric columns, compare boxes, stars and paging. */
export function ResultsTable({
  result,
  columns,
  filteredColumns,
  metricsByKey,
  sectorLabel,
  sort,
  desc,
  onSort,
  page,
  onPage,
  remountKey,
}: {
  result: ScreenResult | null;
  columns: string[];
  /** Columns that have an active condition get a tint. */
  filteredColumns: Set<string>;
  metricsByKey: Map<string, Metric>;
  sectorLabel: Map<string, string>;
  sort: string;
  desc: boolean;
  onSort: (key: string) => void;
  page: number;
  onPage: (page: number) => void;
  /** Changes when the table may have appeared or changed shape (e.g. a new snapshot). */
  remountKey: unknown;
}) {
  const router = useRouter();
  const compare = useCompare();
  const watch = useWatchlist();
  const tableBox = useRef<HTMLDivElement>(null);
  const tableWide = useIsWide(tableBox, remountKey);

  return (
    <>
    <div ref={tableBox} className={`panel results__table ${tableWide ? "is-wide" : ""}`}>
      <table className="table">
        <thead>
          <tr>
            <th scope="col" className="cmp-col">
              <span title={`최대 ${COMPARE_MAX}개까지 담아 나란히 비교해요`}>비교</span>
            </th>
            <th scope="col" className="left ticker-col">
              종목
            </th>
            <th scope="col" className="left">
              섹터
            </th>
            <th scope="col">현재가</th>
            {columns.map((k) => {
              const m = metricsByKey.get(k)!;
              return (
                <th key={k} scope="col" aria-sort={sort === k ? (desc ? "descending" : "ascending") : undefined}>
                  <button type="button" className="sort-btn" aria-sort={sort === k ? (desc ? "descending" : "ascending") : undefined} onClick={() => onSort(k)}>
                    {m.label}
                    {sort === k ? (desc ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              );
            })}
            <th scope="col">
              <span className="sr-only">관심</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {result?.rows.map((r) => (
            <tr
              key={r.symbol}
              className="row-link"
              onClick={(e) => {
                // Let real links, buttons and text selection behave normally.
                if ((e.target as HTMLElement).closest("a, button, input") || window.getSelection()?.toString()) return;
                const href = `/stocks/${r.symbol}`;
                if (e.metaKey || e.ctrlKey) window.open(href, "_blank");
                else router.push(href);
              }}
            >
              <td className="cmp-col">
                <input
                  type="checkbox"
                  aria-label={`${r.symbol} 비교함에 담기`}
                  checked={compare.has(r.symbol)}
                  disabled={!compare.has(r.symbol) && compare.full}
                  onChange={() => compare.toggle(r.symbol)}
                  onClick={(e) => e.stopPropagation()}
                />
              </td>
              <td className="left ticker-col">
                <Link className="ticker" href={`/stocks/${r.symbol}`}>
                  {r.symbol}
                </Link>
                <span className="results__name">{r.name}</span>
                {r.other_classes ? <span className="results__name">같은 회사 다른 주식: {r.other_classes}</span> : null}
              </td>
              <td className="left muted">{sectorLabel.get(r.sector ?? "") ?? r.sector ?? "–"}</td>
              <td>{price(r.price as number | null)}</td>
              {columns.map((k) => (
                <td
                  key={k}
                  className={`${filteredColumns.has(k) ? "is-filtered" : ""} ${SIGNED.has(k) ? direction(r[k] as number | null) : ""}`.trim() || undefined}
                >
                  {metricCell(r[k] as number | null, metricsByKey.get(k)!)}
                </td>
              ))}
              <td>
                <WatchStar
                  symbol={r.symbol}
                  active={watch.has(r.symbol)}
                  onToggle={() =>
                    watch.has(r.symbol)
                      ? watch.remove(r.symbol)
                      : watch.add({ symbol: r.symbol, name: r.name, priceAtAdd: r.price as number | null })
                  }
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {result && result.ready && !result.rows.length ? (
        <p className="note" style={{ margin: 12 }}>
          조건에 맞는 종목이 없어요. 칩의 ×를 눌러 조건을 하나씩 풀어 보세요.
        </p>
      ) : null}
    </div>

    {result && result.total > PAGE_SIZE ? (
      <div className="pager">
        <button className="btn" type="button" disabled={page === 0} onClick={() => onPage(page - 1)}>
          이전
        </button>
        <span className="small muted">
          {page * PAGE_SIZE + 1}–{Math.min(result.total, (page + 1) * PAGE_SIZE)} / {result.total.toLocaleString()}
        </span>
        <button className="btn" type="button" disabled={(page + 1) * PAGE_SIZE >= result.total} onClick={() => onPage(page + 1)}>
          다음
        </button>
      </div>
    ) : null}
    </>
  );
}
