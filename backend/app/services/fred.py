"""FRED (Federal Reserve Economic Data): rates, inflation, jobs, credit."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pandas as pd

from app.cache import ttl_cache
from app.config import settings

BASE = "https://api.stlouisfed.org/fred"


class FredUnavailable(RuntimeError):
    pass


def _get(path: str, **params) -> dict:
    if not settings.fred_api_key:
        raise FredUnavailable("FRED_API_KEY가 backend/.env에 없어요.")
    params |= {"api_key": settings.fred_api_key, "file_type": "json"}
    r = httpx.get(f"{BASE}/{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


@ttl_cache(seconds=60 * 60)
def series(series_id: str, years: int = 10) -> pd.Series:
    """Observations as a float Series indexed by date ('.' = missing is dropped)."""
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    data = _get("series/observations", series_id=series_id, observation_start=start)
    obs = data.get("observations", [])
    s = pd.Series(
        {pd.Timestamp(o["date"]): o["value"] for o in obs},
        dtype="object",
    )
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.name = series_id
    return s


def transform(s: pd.Series, how: str) -> pd.Series:
    """Turn raw levels into what people actually read (e.g. CPI → YoY %)."""
    if how == "yoy":
        # Works for monthly and weekly data alike: compare with ~1 year earlier.
        shifted = s.copy()
        shifted.index = shifted.index + pd.DateOffset(years=1)
        prev = shifted.reindex(s.index, method="nearest", tolerance=pd.Timedelta(days=4))
        return ((s / prev - 1) * 100).dropna()
    if how == "diff":
        return s.diff().dropna()
    return s


# What the macro page shows. unit is what the user sees after the transform.
MACRO_GROUPS = [
    {
        "key": "rates",
        "label": "금리",
        "series": [
            {"id": "DFF", "label": "연방기금금리", "unit": "%", "how": "level"},
            {"id": "DGS2", "label": "미국채 2년", "unit": "%", "how": "level"},
            {"id": "DGS10", "label": "미국채 10년", "unit": "%", "how": "level"},
            {"id": "T10Y2Y", "label": "장단기 금리차 (10년−2년)", "unit": "%p", "how": "level"},
            {"id": "T10Y3M", "label": "장단기 금리차 (10년−3개월)", "unit": "%p", "how": "level"},
            {"id": "MORTGAGE30US", "label": "30년 주택담보대출 금리", "unit": "%", "how": "level"},
        ],
    },
    {
        "key": "inflation",
        "label": "물가",
        "series": [
            {"id": "CPIAUCSL", "label": "CPI (전년비)", "unit": "%", "how": "yoy"},
            {"id": "CPILFESL", "label": "근원 CPI (전년비)", "unit": "%", "how": "yoy"},
            {"id": "PCEPILFE", "label": "근원 PCE (전년비, 연준 목표 2%)", "unit": "%", "how": "yoy"},
            {"id": "T5YIE", "label": "5년 기대인플레이션 (BEI)", "unit": "%", "how": "level"},
        ],
    },
    {
        "key": "jobs",
        "label": "고용",
        "series": [
            {"id": "UNRATE", "label": "실업률", "unit": "%", "how": "level"},
            {"id": "PAYEMS", "label": "비농업 고용 증감 (천 명)", "unit": "K", "how": "diff"},
            {"id": "ICSA", "label": "신규 실업수당 청구 (주간)", "unit": "", "how": "level"},
            {"id": "JTSJOL", "label": "구인 건수 (천 건)", "unit": "K", "how": "level"},
        ],
    },
    {
        "key": "credit",
        "label": "신용·금융여건",
        "series": [
            {"id": "BAMLH0A0HYM2", "label": "하이일드 스프레드", "unit": "%p", "how": "level"},
            {"id": "NFCI", "label": "시카고 연은 금융여건지수 (0 위면 긴축적)", "unit": "", "how": "level"},
        ],
    },
]


# Release names (FRED) worth putting on the calendar, matched by keyword.
KEY_RELEASES = {
    "consumer price index": "CPI 발표",
    "employment situation": "고용보고서 (비농업 고용)",
    "gross domestic product": "GDP 발표",
    "personal income and outlays": "PCE 물가 발표",
    "producer price index": "PPI 발표",
    "advance monthly sales for retail": "소매판매 발표",
    "job openings and labor turnover": "JOLTS 구인 발표",
    "unemployment insurance weekly claims": "주간 실업수당 청구",
}


@ttl_cache(seconds=6 * 60 * 60)
def upcoming_releases(days: int = 45) -> list[dict]:
    today = date.today()
    data = _get(
        "releases/dates",
        realtime_start=today.isoformat(),
        realtime_end=(today + timedelta(days=days)).isoformat(),
        include_release_dates_with_no_data="true",
        sort_order="asc",
        limit=1000,
    )
    events = []
    seen = set()
    for item in data.get("release_dates", []):
        name = item.get("release_name", "")
        lowered = name.lower()
        for keyword, label in KEY_RELEASES.items():
            if keyword in lowered and (item["date"], label) not in seen:
                seen.add((item["date"], label))
                events.append({"date": item["date"], "title": label, "kind": "economic", "source": name})
    return events
