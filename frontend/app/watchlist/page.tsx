"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { Change, ErrorNote } from "@/components/ui";
import { useApi } from "@/lib/api";
import { price, shortDate, signed } from "@/lib/format";
import { useWatchlist } from "@/lib/storage";
import type { Performance, Quote, WatchItem } from "@/lib/types";

function AddForm({ onAdd }: { onAdd: (symbol: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <form
      className="watch-add"
      onSubmit={(e) => {
        e.preventDefault();
        const s = value.trim().toUpperCase();
        if (/^[A-Z0-9.\-]{1,10}$/.test(s)) {
          onAdd(s);
          setValue("");
        }
      }}
    >
      <input className="input" placeholder="티커 입력 (예: MSFT)" value={value} onChange={(e) => setValue(e.target.value)} aria-label="추가할 티커" />
      <button className="btn btn--primary" type="submit" disabled={!value.trim()}>
        추가
      </button>
    </form>
  );
}

/** Looking back: did the stocks I picked do better than just holding the S&P 500? */
function Review({ perf }: { perf: Performance[] }) {
  const done = perf.filter((p) => p.excess_pct != null);
  if (!done.length) return null;
  const beat = done.filter((p) => (p.excess_pct as number) > 0).length;
  const avg = done.reduce((s, p) => s + (p.excess_pct as number), 0) / done.length;
  return (
    <section className="panel" aria-labelledby="review-title">
      <div className="panel__head">
        <h2 id="review-title">복기</h2>
      </div>
      <div className="panel__body">
        <p className="watch-summary">
          <span>
            {done.length}개 중 <b>{beat}개</b>가 같은 기간 S&amp;P 500보다 잘했어요
          </span>
          <span>
            평균 차이 <Change value={avg} digits={1} suffix="%p" />
          </span>
        </p>
        <p className="small muted" style={{ marginTop: 8 }}>
          각 종목을 추가한 날부터 오늘까지를 S&amp;P 500(SPY)과 비교했어요. 결과보다 &apos;관심 사유&apos;가 맞았는지를 같이 돌아보면 더 많이 배울 수 있어요.
          {done.length < 5 ? " 종목 수가 적고 기간이 짧으면 운의 영향이 커요." : ""}
        </p>
      </div>
    </section>
  );
}

function Row({
  item,
  quote,
  perf,
  onChange,
  onRemove,
}: {
  item: WatchItem;
  quote?: Quote;
  perf?: Performance;
  onChange: (p: Partial<WatchItem>) => void;
  onRemove: () => void;
}) {
  const since = perf?.change_pct ?? (quote?.price && item.priceAtAdd ? (quote.price / item.priceAtAdd - 1) * 100 : null);
  const basePrice = perf?.base_price ?? item.priceAtAdd;
  return (
    <li className="panel watch-item">
      <div className="watch-item__head">
        <div>
          <Link href={`/stocks/${item.symbol}`} className="ticker">
            {item.symbol}
          </Link>{" "}
          <span className="muted small">{item.name}</span>
        </div>
        <div className="watch-item__nums small">
          <span>{price(quote?.price)}</span>
          <span>
            오늘 <Change value={quote?.change_pct} />
          </span>
          <span title={basePrice ? `추가 당시 ${price(basePrice)}` : undefined}>
            추가 후 <Change value={since} digits={1} />
          </span>
          {perf?.benchmark_pct != null ? (
            <span className="muted" title={`같은 기간 S&P 500(SPY) ${signed(perf.benchmark_pct, 1, "%")}`}>
              S&amp;P 500 대비 <Change value={perf.excess_pct} digits={1} suffix="%p" />
            </span>
          ) : perf && !perf.base_date ? (
            <span className="muted">비교는 다음 거래일부터</span>
          ) : null}
          <span className="muted">{shortDate(item.addedAt)} 추가</span>
          <button type="button" className="btn btn--ghost small" onClick={onRemove}>
            삭제
          </button>
        </div>
      </div>
      <div className="watch-item__notes">
        <label>
          <span className="small muted">관심 사유</span>
          <input
            className="input"
            placeholder="왜 보고 있나요? 예: 금리 인하 시 수혜, PER 업종 대비 낮음"
            value={item.reason}
            onChange={(e) => onChange({ reason: e.target.value })}
          />
        </label>
        <label>
          <span className="small muted">메모</span>
          <textarea
            className="input"
            rows={2}
            placeholder="확인할 것, 다음 실적에서 볼 숫자, 생각이 바뀌는 조건…"
            value={item.memo}
            onChange={(e) => onChange({ memo: e.target.value })}
          />
        </label>
      </div>
    </li>
  );
}

export default function WatchlistPage() {
  const watch = useWatchlist();
  const fileRef = useRef<HTMLInputElement>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const symbols = watch.items.map((i) => i.symbol).join(",");
  const quotes = useApi<{ quotes: Quote[] }>(symbols ? `/api/quotes?symbols=${encodeURIComponent(symbols)}` : null);
  const bySymbol = new Map((quotes.data?.quotes ?? []).map((q) => [q.symbol, q]));
  const since = watch.items.map((i) => `${i.symbol}:${i.addedAt.slice(0, 10)}`).join(",");
  const perfReq = useApi<{ items: Performance[] }>(since ? `/api/performance?items=${encodeURIComponent(since)}` : null);
  const perf = perfReq.data?.items ?? [];
  const perfBySymbol = new Map(perf.map((p) => [p.symbol, p]));

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(watch.items, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `stock-scout-watchlist-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const importJson = async (file: File) => {
    setImportError(null);
    try {
      const parsed = JSON.parse(await file.text());
      if (!Array.isArray(parsed) || !parsed.every((i) => typeof i?.symbol === "string")) throw new Error();
      const existing = new Set(watch.items.map((i) => i.symbol));
      const incoming = (parsed as (Partial<WatchItem> & { symbol: string })[]).filter((i) => !existing.has(i.symbol));
      watch.replaceAll([...watch.items, ...incoming.map((i) => ({ reason: "", memo: "", addedAt: new Date().toISOString(), ...i }))]);
    } catch {
      setImportError("관심종목 JSON 파일이 아니에요.");
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>관심종목</h1>
        <div className="watch-tools">
          <button className="btn" type="button" onClick={exportJson} disabled={!watch.items.length}>
            내보내기
          </button>
          <button className="btn" type="button" onClick={() => fileRef.current?.click()}>
            가져오기
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/json"
            hidden
            onChange={(e) => e.target.files?.[0] && importJson(e.target.files[0])}
          />
        </div>
      </div>

      <AddForm onAdd={(symbol) => watch.add({ symbol })} />
      {importError ? <ErrorNote message={importError} /> : null}
      {quotes.error ? <ErrorNote message={quotes.error} onRetry={quotes.reload} /> : null}

      {watch.items.length ? <Review perf={perf} /> : null}

      {watch.items.length ? (
        <ul className="watch-list">
          {watch.items.map((item) => (
            <Row
              key={item.symbol}
              item={item}
              quote={bySymbol.get(item.symbol)}
              perf={perfBySymbol.get(item.symbol)}
              onChange={(p) => watch.update(item.symbol, p)}
              onRemove={() => watch.remove(item.symbol)}
            />
          ))}
        </ul>
      ) : (
        <p className="note">
          아직 관심종목이 없어요. 스크리너나 종목 화면에서 ☆를 누르거나 위에 티커를 입력해 추가하세요. 관심 사유를 적어 두면 나중에 판단을 돌아볼 때
          도움이 돼요.
        </p>
      )}

      <p className="disclaimer">관심종목과 메모는 이 브라우저에만 저장돼요. 다른 기기로 옮기려면 내보내기/가져오기를 쓰세요.</p>
    </>
  );
}
