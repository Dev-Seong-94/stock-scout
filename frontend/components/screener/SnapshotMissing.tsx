"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Catalog } from "@/lib/types";

export function SnapshotMissing({ catalog, onBuilt }: { catalog: Catalog; onBuilt: () => void }) {
  const [status, setStatus] = useState(catalog.status);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!status.running) return;
    const t = window.setInterval(async () => {
      const s = await api<{ status: Catalog["status"] }>("/api/screener/status").catch(() => null);
      if (!s) return;
      setStatus(s.status);
      if (!s.status.running) {
        window.clearInterval(t);
        if (!s.status.error) onBuilt();
      }
    }, 3000);
    return () => window.clearInterval(t);
  }, [status.running, onBuilt]);

  const start = async () => {
    setError(null);
    try {
      const r = await api<{ status: Catalog["status"] }>("/api/screener/refresh", { method: "POST" });
      setStatus(r.status);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="note">
      <p>
        <b>스크리너 데이터가 아직 없어요.</b> 종목 지표는 하루에 한 번 미리 계산해 두고 그걸 필터해요. 터미널에서{" "}
        <code>python -m scripts.build_snapshot</code>을 실행하거나 아래 버튼을 눌러 주세요. S&amp;P 500 + 나스닥 100 기준 10–20분
        정도 걸려요.
      </p>
      <p style={{ marginTop: 10 }}>
        {status.running ? (
          <span>
            만드는 중… {status.done}/{status.total}
          </span>
        ) : (
          <button className="btn btn--primary" type="button" onClick={start}>
            지금 만들기
          </button>
        )}
      </p>
      {status.error || error ? <p className="small" style={{ marginTop: 8 }}>오류: {status.error ?? error}</p> : null}
    </div>
  );
}
