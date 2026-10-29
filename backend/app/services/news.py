"""Headlines from GDELT (global news index) and RSS feeds."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import feedparser
import httpx

from app.cache import ttl_cache

log = logging.getLogger(__name__)

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"

# Topics for the geopolitics tab. Edit freely; queries use GDELT syntax
# (parentheses are only allowed around OR'd terms).
GEO_TOPICS = [
    {"key": "trade", "label": "무역·관세", "query": '(tariff OR tariffs OR "trade war" OR "export controls")'},
    {"key": "us-china", "label": "미중 관계", "query": '"United States" China (tension OR talks OR sanctions OR chips)'},
    {"key": "middle-east", "label": "중동", "query": "(Israel OR Iran OR Gaza OR \"Red Sea\" OR Houthi)"},
    {"key": "russia-ukraine", "label": "러시아·우크라이나", "query": "Russia Ukraine (war OR ceasefire OR sanctions)"},
    {"key": "energy", "label": "에너지·원자재", "query": "(OPEC OR \"oil supply\" OR \"natural gas\" OR \"crude oil\")"},
    {"key": "central-banks", "label": "중앙은행", "query": '("Federal Reserve" OR "rate cut" OR "rate hike" OR ECB OR "Bank of Japan")'},
]

# Market-wide headline feeds for the dashboard. Add or remove as you like.
RSS_FEEDS = [
    {"name": "Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml"},
    {"name": "CNBC Markets", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"name": "MarketWatch", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
]


def _gdelt_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return value


class GdeltUnavailable(RuntimeError):
    pass


# GDELT allows one request every 5 seconds per client; space calls out.
_GDELT_INTERVAL = 5.5
_gdelt_lock = threading.Lock()
_gdelt_last = 0.0


def _gdelt_get(params: dict) -> httpx.Response:
    global _gdelt_last
    with _gdelt_lock:
        wait = _gdelt_last + _GDELT_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            return httpx.get(GDELT, params=params, timeout=20)
        finally:
            _gdelt_last = time.monotonic()


@ttl_cache(seconds=30 * 60)
def gdelt(query: str, timespan: str = "7d", limit: int = 25) -> list[dict]:
    """Raises GdeltUnavailable on failure so the empty result is not cached."""
    params = {
        "query": f"{query} sourcelang:english",
        "mode": "ArtList",
        "format": "json",
        "maxrecords": limit,
        "timespan": timespan,
        "sort": "DateDesc",
    }
    try:
        r = _gdelt_get(params)
        if r.status_code == 429:
            r = _gdelt_get(params)
        r.raise_for_status()
        if "json" not in r.headers.get("content-type", ""):
            # Query errors come back as 200 + a plain-text message.
            raise ValueError(r.text[:200])
        articles = r.json().get("articles", [])
    except Exception as exc:  # GDELT sometimes answers with HTML or rate limits
        log.warning("GDELT failed for %r: %s", query, exc)
        raise GdeltUnavailable("GDELT가 잠시 응답하지 않아요. 조금 뒤에 다시 시도해 주세요.") from exc
    seen, out = set(), []
    for a in articles:
        title = (a.get("title") or "").strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        out.append(
            {
                "title": title,
                "url": a.get("url"),
                "source": a.get("domain"),
                "published": _gdelt_date(a.get("seendate")),
                "country": a.get("sourcecountry"),
            }
        )
    return out


@ttl_cache(seconds=30 * 60)
def rss(limit_per_feed: int = 8) -> list[dict]:
    items = []
    for feed in RSS_FEEDS:
        try:
            # Fetch with httpx (certifi CA bundle): feedparser's own urllib fetch fails
            # certificate checks on python.org builds of Python for macOS.
            r = httpx.get(feed["url"], timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (stock-scout)"})
            r.raise_for_status()
            parsed = feedparser.parse(r.content)
        except Exception as exc:
            log.warning("RSS %s failed: %s", feed["name"], exc)
            continue
        for e in parsed.entries[:limit_per_feed]:
            published = None
            if getattr(e, "published_parsed", None):
                published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).isoformat()
            items.append({"title": e.get("title"), "url": e.get("link"), "source": feed["name"], "published": published})
    items = [i for i in items if i["title"] and i["url"]]
    items.sort(key=lambda i: i["published"] or "", reverse=True)
    return items
