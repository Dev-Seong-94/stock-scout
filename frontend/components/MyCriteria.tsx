"use client";

import { useState } from "react";

import { answerLabel, QUESTIONS, type Profile } from "@/lib/criteria";
import { useProfile } from "@/lib/storage";

/** The three "내 기준" questions; saves once all are answered. */
export function CriteriaForm({ onDone }: { onDone?: () => void }) {
  const [profile, setProfile] = useProfile();
  const [draft, setDraft] = useState<Partial<Profile>>(profile ?? {});
  const complete = QUESTIONS.every((q) => draft[q.key]);

  return (
    <div className="criteria">
      {QUESTIONS.map((q) => (
        <fieldset key={q.key} className="criteria__q">
          <legend className="small">{q.title}</legend>
          <div className="criteria__options">
            {q.options.map((o) => (
              <button
                key={o.value}
                type="button"
                className="mode-toggle"
                aria-pressed={draft[q.key] === o.value}
                onClick={() => setDraft((d) => ({ ...d, [q.key]: o.value }))}
              >
                {o.label}
              </button>
            ))}
          </div>
        </fieldset>
      ))}
      <div className="criteria__actions">
        <button
          type="button"
          className="btn btn--primary"
          disabled={!complete}
          onClick={() => {
            setProfile(draft as Profile);
            onDone?.();
          }}
        >
          이 기준으로 보기
        </button>
        <span className="small muted">답은 이 브라우저에만 저장되고, 보여 주는 순서만 바꿔요. 걸러 내지는 않아요.</span>
      </div>
    </div>
  );
}

/** One line with the saved answers and a way to change them. */
export function CriteriaSummary() {
  const [profile] = useProfile();
  const [editing, setEditing] = useState(false);
  if (!profile) return null;
  if (editing) return <CriteriaForm onDone={() => setEditing(false)} />;
  return (
    <p className="criteria__summary small">
      <span className="muted">내 기준</span> <b>{answerLabel(profile)}</b>{" "}
      <button type="button" className="btn btn--ghost small" onClick={() => setEditing(true)}>
        바꾸기
      </button>
    </p>
  );
}
