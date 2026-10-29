"""Event calendar: FOMC meetings, key US data releases, earnings dates."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

import httpx

from app.cache import ttl_cache
from app.config import settings
from app.services import fred

log = logging.getLogger(__name__)


def fomc_events(start: date, end: date) -> list[dict]:
    path = settings.data_dir / "fomc.json"
    if not path.exists():
        return []
    meetings = json.loads(path.read_text()).get("meetings", [])
    events = []
    for m in meetings:
        decision = date.fromisoformat(m["end"])
        if start <= decision <= end:
            title = "FOMC 금리 결정" + (" (점도표 공개)" if m.get("sep") else "")
            events.append({"date": m["end"], "title": title, "kind": "fomc", "source": "Federal Reserve"})
    return events


@ttl_cache(seconds=6 * 60 * 60)
def earnings(start: date, end: date, symbols: tuple[str, ...] = ()) -> list[dict]:
    """Earnings dates from Finnhub (optional key). Filtered to symbols if given."""
    if not settings.finnhub_api_key:
        return []
    try:
        r = httpx.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={"from": start.isoformat(), "to": end.isoformat(), "token": settings.finnhub_api_key},
            timeout=20,
        )
        r.raise_for_status()
        rows = r.json().get("earningsCalendar", [])
    except Exception as exc:
        log.warning("Finnhub earnings failed: %s", exc)
        return []
    wanted = {s.upper() for s in symbols}
    events = []
    for row in rows:
        sym = row.get("symbol", "")
        if wanted and sym not in wanted:
            continue
        when = {"bmo": "장 시작 전", "amc": "장 마감 후"}.get(row.get("hour", ""), "")
        events.append(
            {
                "date": row["date"],
                "title": f"{sym} 실적 발표" + (f" ({when})" if when else ""),
                "kind": "earnings",
                "symbol": sym,
                "source": "Finnhub",
            }
        )
    return events


def upcoming(days: int = 30, symbols: tuple[str, ...] = ()) -> dict:
    start = date.today()
    end = start + timedelta(days=days)
    events: list[dict] = fomc_events(start, end)
    notes: list[str] = []
    try:
        events += [e for e in fred.upcoming_releases(days) if e["date"] <= end.isoformat()]
    except fred.FredUnavailable as exc:
        notes.append(str(exc))
    except Exception as exc:
        log.warning("FRED release dates failed: %s", exc)
        notes.append("FRED 발표 일정을 불러오지 못했어요.")
    if settings.finnhub_api_key:
        events += earnings(start, end, symbols)
    else:
        notes.append("실적 발표 일정은 FINNHUB_API_KEY를 넣으면 표시돼요.")
    events.sort(key=lambda e: (e["date"], e["kind"]))
    return {"events": events, "notes": notes}
