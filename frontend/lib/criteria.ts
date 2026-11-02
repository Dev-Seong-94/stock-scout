// "내 기준": three questions about the user's own situation. The answers only
// change what is shown first (which example combinations, which metrics);
// they never filter anything out or say what to buy.

export type Horizon = "long" | "mid" | "short";
export type Drawdown = "low" | "mid" | "high";
export type Goal = "income" | "growth" | "value" | "rebound";
export type Profile = { horizon: Horizon; drawdown: Drawdown; goal: Goal };

export const QUESTIONS = [
  {
    key: "horizon",
    title: "이 돈을 얼마나 오래 둘 수 있나요?",
    options: [
      { value: "long", label: "3년 이상" },
      { value: "mid", label: "1~3년" },
      { value: "short", label: "1년 안에 쓸 수도 있어요" },
    ],
  },
  {
    key: "drawdown",
    title: "계좌가 잠시 얼마나 빠져도 버틸 수 있나요?",
    options: [
      { value: "low", label: "−10%도 불편해요" },
      { value: "mid", label: "−20~30%까지는 괜찮아요" },
      { value: "high", label: "−50%도 각오해요" },
    ],
  },
  {
    key: "goal",
    title: "무엇을 기대하나요?",
    options: [
      { value: "income", label: "꾸준한 배당" },
      { value: "growth", label: "회사가 크는 것" },
      { value: "value", label: "좋은 회사를 덜 비싸게" },
      { value: "rebound", label: "많이 빠진 이유 파고들기" },
    ],
  },
] as const;

export function answerLabel(p: Profile): string {
  return QUESTIONS.map((q) => q.options.find((o) => o.value === p[q.key])?.label).join(" · ");
}

// What each example combination suits, by preset id.
const FIT: Record<string, { goal: Goal; drawdown: Drawdown[]; horizon: Horizon[] }> = {
  "quality-value": { goal: "value", drawdown: ["low", "mid", "high"], horizon: ["long", "mid"] },
  "growth-momentum": { goal: "growth", drawdown: ["mid", "high"], horizon: ["long", "mid"] },
  "oversold-large": { goal: "rebound", drawdown: ["mid", "high"], horizon: ["long", "mid"] },
  "steady-income": { goal: "income", drawdown: ["low", "mid", "high"], horizon: ["long", "mid", "short"] },
  "funded-growth": { goal: "growth", drawdown: ["high"], horizon: ["long"] },
};

export type Fit = { score: number; goal: boolean; warnings: string[] };

export function presetFit(id: string, p: Profile): Fit | null {
  const f = FIT[id];
  if (!f) return null;
  const warnings: string[] = [];
  if (!f.drawdown.includes(p.drawdown)) warnings.push("주가가 크게 흔들리는 종목이 많아서, 버틸 수 있는 하락 폭과 안 맞을 수 있어요.");
  if (!f.horizon.includes(p.horizon)) warnings.push("회복이나 성장에 시간이 걸리는 경우가 많아서, 두는 기간과 안 맞을 수 있어요.");
  const goal = f.goal === p.goal;
  return { score: (goal ? 2 : 0) - warnings.length, goal, warnings };
}

/** Metrics worth looking at first for these answers (shown on top in the screener and compare view). */
export function focusMetrics(p: Profile): string[] {
  const byGoal: Record<Goal, string[]> = {
    income: ["dividend_yield", "fcf_yield", "debt_to_equity", "interest_coverage"],
    growth: ["revenue_growth", "gross_margin", "ps", "dist_sma200"],
    value: ["pe", "roe", "operating_margin", "fcf_yield"],
    rebound: ["from_52w_high", "rsi14", "ret_3m", "forward_pe"],
  };
  const byDrawdown: Record<Drawdown, string[]> = {
    low: ["volatility_3m", "debt_to_equity"],
    mid: ["volatility_3m"],
    high: ["cash_runway"],
  };
  return [...new Set([...byGoal[p.goal], ...byDrawdown[p.drawdown]])];
}

export const SHORT_HORIZON_NOTE = "1년 안에 쓸 수도 있는 돈은 주가가 회복할 시간이 부족할 수 있어요. 어떤 조합이든 이 점을 같이 생각해 보세요.";
