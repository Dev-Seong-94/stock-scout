"use client";

import { useState } from "react";

import { CriteriaForm, CriteriaSummary } from "@/components/MyCriteria";
import { presetFit, SHORT_HORIZON_NOTE, type Profile } from "@/lib/criteria";
import type { Preset } from "@/lib/types";

/** First screen: the "내 기준" questions, then example combinations ordered by them. */
export function StartHere({
  presets,
  profile,
  onPick,
  onFindCheap,
  onSkip,
}: {
  presets: Preset[];
  profile: Profile | null;
  onPick: (p: Preset) => void;
  onFindCheap: () => void;
  onSkip: () => void;
}) {
  // Names only by default so the results table stays near the top; the notes
  // and warnings are one click away (and in each button's tooltip).
  const [detailed, setDetailed] = useState(false);
  const fits = new Map(presets.map((p) => [p.id, profile ? presetFit(p.id, profile) : null]));
  const ordered = profile ? [...presets].sort((a, b) => (fits.get(b.id)?.score ?? 0) - (fits.get(a.id)?.score ?? 0)) : presets;
  return (
    <section className={`panel start-here ${detailed ? "" : "start-here--compact"}`} aria-labelledby="start-here-title">
      <div className="start-here__head">
        <div>
          <h2 id="start-here-title">어디서 시작할까요?</h2>
          <p className="small muted">
            {profile
              ? "내 기준에 맞춰 예시 조합의 순서를 바꿨어요. 추천이 아니라 거르는 방법의 예시예요."
              : "먼저 세 가지만 답해 주세요. 답에 맞춰 예시 조합과 먼저 볼 지표를 앞에 놓아 드려요."}
          </p>
        </div>
        <button type="button" className="btn btn--ghost small" onClick={onSkip}>
          직접 고를게요
        </button>
      </div>
      <div className="start-cheap">
        <button type="button" className="btn btn--primary" onClick={onFindCheap}>
          가치보다 싸 보이는 후보 찾기
        </button>
        <p className="small muted">업종 대비, 자기 과거 대비, 현금 기준으로 비교해서 조건을 많이 충족한 종목부터 보여 줘요. 뭘 골라야 할지 모르겠다면 여기서 시작해 보세요.</p>
      </div>
      {profile ? <CriteriaSummary /> : <CriteriaForm />}
      {profile?.horizon === "short" ? <p className="note small">{SHORT_HORIZON_NOTE}</p> : null}
      <div className="start-here__presets-head">
        <h3 className="small">예시 조합</h3>
        <button type="button" className="btn btn--ghost small" aria-expanded={detailed} onClick={() => setDetailed((d) => !d)}>
          {detailed ? "이름만 보기" : "설명 함께 보기"}
        </button>
      </div>
      <ul className="start-here__list">
        {ordered.map((p) => {
          const fit = fits.get(p.id);
          const warnings = fit?.warnings ?? [];
          return (
            <li key={p.id}>
              <button
                type="button"
                className={`start-card ${fit && fit.score < 1 ? "is-dim" : ""}`}
                title={detailed ? undefined : [p.note, ...warnings].filter(Boolean).join("\n") || undefined}
                onClick={() => onPick(p)}
              >
                {fit?.goal ? <span className="start-card__badge small">기대와 맞아요</span> : null}
                <b>{p.name}</b>
                {!detailed && warnings.length ? <span className="start-card__warn small">주의 {warnings.length}</span> : null}
                {detailed && p.note ? <span className="small muted">{p.note}</span> : null}
                {detailed
                  ? warnings.map((w) => (
                      <span key={w} className="start-card__warn small">
                        {w}
                      </span>
                    ))
                  : null}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
