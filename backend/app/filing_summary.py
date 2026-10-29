"""Plain-Korean one-liners for SEC filings. Pure parsing, no network.

Form 4 (insider trades) and Form 144 (notice of a planned sale) are XML, so
they can be summarised exactly. 8-K item numbers come from EDGAR's index.
Longer reports (10-K, 10-Q) are not summarised; the UI says what to read.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

# Form 4 transaction codes, with what they mean for someone new to this.
TX_CODES = {
    "P": ("장내 매수", "본인 돈으로 시장에서 산 거래예요."),
    "S": ("장내 매도", "시장에서 판 거래예요."),
    "A": ("보상으로 주식 받음", "회사가 급여·보상으로 준 주식이에요. 사고판 게 아니에요."),
    "M": ("스톡옵션·RSU 행사", "보상으로 받은 권리를 실제 주식으로 바꾼 거예요."),
    "X": ("스톡옵션 행사", "보상으로 받은 권리를 실제 주식으로 바꾼 거예요."),
    "F": ("세금용 주식 반납", "보상 주식에 붙는 세금을 내려고 회사에 넘긴 거예요. 시장에서 판 게 아니에요."),
    "G": ("증여", "가족·재단 등에 무상으로 준 거예요."),
    "D": ("회사에 반납", "회사에 주식을 돌려준 거예요."),
    "C": ("다른 증권으로 전환", "전환사채·우선주 등을 주식으로 바꾼 거예요."),
    "W": ("상속", "상속으로 주식이 옮겨간 거예요."),
    "J": ("기타 거래", "위 유형에 안 맞는 거래예요. 원문 각주를 보세요."),
}

# 8-K item numbers → what happened.
EIGHT_K_ITEMS = {
    "1.01": "중요 계약 체결",
    "1.02": "중요 계약 종료",
    "1.03": "파산·회생 절차",
    "1.05": "사이버 보안 사고",
    "2.01": "인수·자산 매각 완료",
    "2.02": "실적 발표",
    "2.03": "새 부채(차입·채권 발행)",
    "2.05": "구조조정·사업 철수 비용",
    "2.06": "자산 손상(손실 처리)",
    "3.01": "상장 유지 요건 미달·상장 이전",
    "3.02": "비공개 주식 발행",
    "3.03": "주주 권리 변경",
    "4.01": "감사인 변경",
    "4.02": "과거 재무제표 신뢰 불가(정정)",
    "5.01": "경영권 변동",
    "5.02": "임원·이사 선임/사임 또는 보수 변경",
    "5.03": "정관 변경",
    "5.07": "주주총회 투표 결과",
    "7.01": "투자자 대상 자료 공개",
    "8.01": "기타 주요 사항",
    "9.01": "첨부 자료",
}

# What each form is, for the glossary and for rows without a parsed summary.
FORM_HELP = {
    "10-K": "1년 실적과 사업·위험 요인을 담은 연간 보고서예요. 'Risk Factors'와 'Management's Discussion(MD&A)'부터 읽어 보세요.",
    "10-Q": "분기 실적 보고서예요. 'Management's Discussion(MD&A)'에 회사가 설명하는 실적 변화 이유가 있어요.",
    "8-K": "실적 발표, 임원 교체, 큰 계약처럼 중요한 일이 생기면 4영업일 안에 내는 수시 공시예요.",
    "4": "임원·이사·10% 이상 대주주가 주식을 사고팔거나 받으면 2영업일 안에 내는 서류예요.",
    "3": "새로 내부자가 된 사람이 처음 보유 주식을 신고하는 서류예요.",
    "144": "내부자가 주식을 팔기 전에 '이만큼 팔 예정'이라고 미리 내는 신고예요. 실제 매도는 뒤에 Form 4로 나와요.",
    "DEF 14A": "주주총회 안건과 임원 보수가 담긴 안내문이에요.",
    "SC 13G": "어떤 투자자가 지분 5% 이상을 단순 투자 목적으로 가졌다는 신고예요.",
    "SC 13D": "어떤 투자자가 지분 5% 이상을 경영 참여 목적으로 가졌다는 신고예요.",
    "S-8": "직원 보상용 주식을 발행하겠다는 등록 서류예요.",
}


def _text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path)
    return (found.text or "").strip() if found is not None and found.text else ""


def _num(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _strip_ns(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def person_name(raw: str) -> str:
    """'COXE TENCH' → 'Tench Coxe'. SEC lists people last name first."""
    parts = raw.replace(",", " ").split()
    if not parts:
        return raw
    entity = {"LLC", "INC", "INC.", "LP", "L.P.", "CORP", "TRUST", "FUND", "LTD", "CO", "PARTNERS"}
    if len(parts) > 4 or any(p.upper() in entity for p in parts):
        return raw.title()
    return " ".join(p.capitalize() if not p.endswith(".") else p.upper() for p in parts[1:] + parts[:1])


def money(v: float) -> str:
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    if v >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"


def _role(owner: ET.Element | None) -> str:
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    if rel is None:
        return ""
    title = _text(rel, "officerTitle")
    roles = []
    if _text(rel, "isOfficer") in ("1", "true"):
        roles.append(title or "임원")
    if _text(rel, "isDirector") in ("1", "true"):
        roles.append("이사")
    if _text(rel, "isTenPercentOwner") in ("1", "true"):
        roles.append("10% 이상 대주주")
    return ", ".join(roles)


def summarize_form4(xml: str) -> dict | None:
    """{'text', 'note', 'kind'}: who did what, how much, and what it means."""
    try:
        root = _strip_ns(ET.fromstring(xml))
    except ET.ParseError:
        return None
    owner = root.find("reportingOwner")
    name = person_name(_text(owner, "reportingOwnerId/rptOwnerName"))
    role = _role(owner)

    totals: dict[str, list[float]] = {}  # code → [shares, value, priced shares]
    rows = root.findall("nonDerivativeTable/nonDerivativeTransaction") or root.findall("derivativeTable/derivativeTransaction")
    for tx in rows:
        code = _text(tx, "transactionCoding/transactionCode")
        shares = _num(_text(tx, "transactionAmounts/transactionShares/value")) or 0.0
        price = _num(_text(tx, "transactionAmounts/transactionPricePerShare/value")) or 0.0
        t = totals.setdefault(code, [0.0, 0.0, 0.0])
        t[0] += shares
        if price > 0:
            t[1] += shares * price
            t[2] += shares
    if not totals:
        return {"text": f"{name} ({role}) 보유 현황 보고" if role else f"{name} 보유 현황 보고", "note": "거래 없이 보유 주식만 알린 서류예요.", "kind": "other"}

    # The biggest transaction type leads; open-market buys and sells first.
    order = sorted(totals, key=lambda c: (c not in ("P", "S"), -totals[c][0]))
    parts = []
    for code in order[:2]:
        shares, value, priced = totals[code]
        label = TX_CODES.get(code, ("기타 거래", ""))[0]
        piece = f"{label} {shares:,.0f}주"
        if value > 0 and code in ("P", "S"):
            piece += f" (평균 ${value / priced:,.2f}, 약 {money(value)})"
        parts.append(piece)
    lead = order[0]
    note = TX_CODES.get(lead, ("", ""))[1]
    if _text(root, "aff10b5One") in ("1", "true") and lead in ("S", "P", "G"):
        note += " 미리 정해 둔 매매 계획(10b5-1)에 따른 거래예요."
    who = f"{name} ({role})" if role else name
    return {
        "text": f"{who} · " + " · ".join(parts),
        "note": note.strip(),
        "kind": {"P": "buy", "S": "sell"}.get(lead, "other"),
    }


def _date(value: str) -> str:
    try:
        return datetime.strptime(value, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return value


def _acquired_how(raw: str) -> str:
    low = raw.lower()
    if any(k in low for k in ("rsu", "psu", "compensation", "performance", "restricted", "option", "espp")):
        return "회사 보상(주식 보상·스톡옵션)"
    if "open market" in low or "purchase" in low:
        return "시장 매수"
    if "private" in low:
        return "비공개 배정"
    if "gift" in low:
        return "증여"
    return ""


def summarize_144(xml: str) -> dict | None:
    try:
        root = _strip_ns(ET.fromstring(xml))
    except ET.ParseError:
        return None
    info = root.find("formData/issuerInfo")
    sec = root.find("formData/securitiesInformation")
    # Form 144 has no fixed name order (both "Kress Colette" and "Colette Kress" occur).
    name = _text(info, "nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold").title()
    role = {"Officer": "임원", "Director": "이사", "10% Securityholder": "10% 이상 대주주"}.get(_text(info, "relationshipsToIssuer/relationshipToIssuer"), "")
    shares = _num(_text(sec, "noOfUnitsSold"))
    value = _num(_text(sec, "aggregateMarketValue"))
    when = _date(_text(sec, "approxSaleDate"))
    if shares is None:
        return None
    who = f"{name} ({role})" if role else name
    amount = f"{shares:,.0f}주" + (f" (약 {money(value)})" if value else "")
    source = _acquired_how(_text(root, "formData/securitiesToBeSold/natureOfAcquisitionTransaction"))
    note = "매도 예정 신고예요. 실제로 팔면 Form 4가 따로 나와요."
    if source:
        note += f" 팔 주식의 출처: {source}."
    return {"text": f"{who} · {amount}를 {when}쯤 팔 예정", "note": note, "kind": "sell"}


def summarize_8k(items: str) -> dict | None:
    codes = [c.strip() for c in (items or "").split(",") if c.strip() and c.strip() != "9.01"]
    if not codes:
        return None
    labels = [EIGHT_K_ITEMS.get(c, f"항목 {c}") for c in codes]
    return {"text": " · ".join(labels), "note": "", "kind": "other"}


def form_help(form: str) -> str:
    base = form.removesuffix("/A")
    return FORM_HELP.get(base, "")
