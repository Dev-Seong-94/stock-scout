"""SEC EDGAR: company filings (10-K, 10-Q, 8-K, Form 4 …).

The SEC requires a User-Agent with your name and email (SEC_USER_AGENT) and
asks clients to stay under 10 requests per second.
"""

from __future__ import annotations

import httpx

from app.cache import ttl_cache
from app.config import settings

# Plain-language Korean names for the filings people look at most.
FORM_LABELS = {
    "10-K": "연간 보고서",
    "10-Q": "분기 보고서",
    "8-K": "주요 사항 보고 (수시 공시)",
    "4": "내부자 거래 보고",
    "3": "내부자 최초 보유 보고",
    "SC 13D": "5% 이상 대량 보유 (경영 참여 목적)",
    "SC 13G": "5% 이상 대량 보유 (단순 투자)",
    "SCHEDULE 13D": "5% 이상 대량 보유 (경영 참여 목적)",
    "SCHEDULE 13G": "5% 이상 대량 보유 (단순 투자)",
    "DEF 14A": "주주총회 안내 (위임장)",
    "S-1": "신규 상장 신고",
    "S-3": "증권 발행 신고",
    "424B": "증권 발행 설명서",
    "20-F": "외국 기업 연간 보고서",
    "6-K": "외국 기업 수시 보고",
    "13F-HR": "기관 보유 현황",
}


class SecUnavailable(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.sec_user_agent:
        raise SecUnavailable("SEC_USER_AGENT가 backend/.env에 없어요. 예: 'Kihyeok Seong you@example.com'")
    return {"User-Agent": settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"}


@ttl_cache(seconds=24 * 60 * 60)
def ticker_to_cik() -> dict[str, int]:
    r = httpx.get("https://www.sec.gov/files/company_tickers.json", headers=_headers(), timeout=30)
    r.raise_for_status()
    return {row["ticker"].upper(): int(row["cik_str"]) for row in r.json().values()}


def _label(form: str) -> str:
    if form in FORM_LABELS:
        return FORM_LABELS[form]
    for prefix, label in FORM_LABELS.items():
        if form.startswith(prefix):
            return label
    return ""


@ttl_cache(seconds=60 * 60)
def filings(ticker: str, limit: int = 30) -> list[dict]:
    cik = ticker_to_cik().get(ticker.upper().replace("-", "."))
    if cik is None:
        cik = ticker_to_cik().get(ticker.upper())
    if cik is None:
        return []
    r = httpx.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_headers(), timeout=30)
    r.raise_for_status()
    recent = r.json().get("filings", {}).get("recent", {})
    rows = []
    for i, form in enumerate(recent.get("form", [])[:limit]):
        accession = recent["accessionNumber"][i]
        doc = recent["primaryDocument"][i]
        rows.append(
            {
                "form": form,
                "label": _label(form),
                "date": recent["filingDate"][i],
                "description": recent.get("primaryDocDescription", [""] * (i + 1))[i] or "",
                "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{doc}",
            }
        )
    return rows
