"""Plain-language reading of the market backdrop.

Fixed, published rules over the dashboard numbers. It describes the current
state; it does not predict anything or say what to buy.
"""

from __future__ import annotations


def _signal(label: str, tone: str, text: str) -> dict:
    # tone: "calm" (안정), "watch" (주의), "stress" (경계)
    return {"label": label, "tone": tone, "text": text}


def read_regime(ind: dict[str, dict]) -> list[dict]:
    """ind: dashboard indicators keyed by id, each with value/change_1m/percentile."""
    out = []

    vix = ind.get("vix", {}).get("value")
    if vix is not None:
        if vix < 15:
            out.append(_signal("변동성", "calm", f"VIX {vix:.1f}: 시장이 큰 흔들림을 예상하지 않는 구간이에요."))
        elif vix < 25:
            out.append(_signal("변동성", "watch", f"VIX {vix:.1f}: 평균적인 수준의 불안감이에요."))
        else:
            out.append(_signal("변동성", "stress", f"VIX {vix:.1f}: 불안이 큰 구간이에요. 하루 변동폭이 커지기 쉬워요."))

    spx = ind.get("spx", {})
    if spx.get("dist_sma200") is not None:
        d = spx["dist_sma200"]
        tone = "calm" if d > 0 else "stress"
        side = "위" if d > 0 else "아래"
        out.append(_signal("추세", tone, f"S&P 500이 200일 이동평균보다 {abs(d):.1f}% {side}에 있어요."))

    curve = ind.get("curve", {}).get("value")
    if curve is not None:
        if curve < 0:
            out.append(_signal("금리 곡선", "stress", f"10년−2년 금리차 {curve:+.2f}%p: 역전 상태예요. 과거엔 경기 둔화에 앞서 나타난 경우가 많았어요."))
        elif curve < 0.5:
            out.append(_signal("금리 곡선", "watch", f"10년−2년 금리차 {curve:+.2f}%p: 평평한 편이에요."))
        else:
            out.append(_signal("금리 곡선", "calm", f"10년−2년 금리차 {curve:+.2f}%p: 정상적인 우상향 곡선이에요."))

    hy = ind.get("hy", {}).get("value")
    if hy is not None:
        if hy < 3.5:
            out.append(_signal("신용", "calm", f"하이일드 스프레드 {hy:.2f}%p: 회사채 시장이 위험을 크게 걱정하지 않아요."))
        elif hy < 5:
            out.append(_signal("신용", "watch", f"하이일드 스프레드 {hy:.2f}%p: 평균 수준이에요."))
        else:
            out.append(_signal("신용", "stress", f"하이일드 스프레드 {hy:.2f}%p: 신용 위험에 대한 경계가 커진 상태예요."))

    ten = ind.get("us10y", {})
    if ten.get("change_1m") is not None:
        c = ten["change_1m"]
        if abs(c) >= 0.25:
            direction = "올라" if c > 0 else "내려"
            note = "성장주·장기채에 부담이 되기 쉬운 움직임이에요." if c > 0 else "할인율이 낮아지는 움직임이에요."
            out.append(_signal("금리 방향", "watch", f"10년물 금리가 한 달 새 {abs(c):.2f}%p {direction}갔어요. {note}"))

    dxy = ind.get("dxy", {})
    if dxy.get("change_1m") is not None and abs(dxy["change_1m"]) >= 2:
        c = dxy["change_1m"]
        effect = "해외 매출 비중이 큰 미국 기업 실적에 불리한" if c > 0 else "해외 매출 비중이 큰 미국 기업 실적에 유리한"
        out.append(_signal("달러", "watch", f"달러 인덱스가 한 달 새 {c:+.1f}% 움직였어요. {effect} 방향이에요."))

    oil = ind.get("wti", {})
    if oil.get("change_1m") is not None and abs(oil["change_1m"]) >= 10:
        c = oil["change_1m"]
        out.append(_signal("유가", "watch", f"WTI가 한 달 새 {c:+.1f}% 움직였어요. 에너지·운송 업종과 물가 지표에 영향을 줘요."))

    return out
