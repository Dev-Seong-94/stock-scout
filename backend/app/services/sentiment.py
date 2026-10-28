"""CNN Fear & Greed index.

CNN has no public API. This reads the JSON its own page uses, so it can break
without notice; callers must treat None as "not available right now".
"""

from __future__ import annotations

import logging

import httpx

from app.cache import ttl_cache

log = logging.getLogger(__name__)

URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

LABELS = {
    "extreme fear": "극단적 공포",
    "fear": "공포",
    "neutral": "중립",
    "greed": "탐욕",
    "extreme greed": "극단적 탐욕",
}


@ttl_cache(seconds=60 * 60)
def fear_greed() -> dict | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
        "Referer": "https://edition.cnn.com/",
        "Accept": "application/json",
    }
    try:
        r = httpx.get(URL, headers=headers, timeout=15)
        r.raise_for_status()
        fg = r.json()["fear_and_greed"]
        history = r.json().get("fear_and_greed_historical", {}).get("data", [])
    except Exception as exc:
        log.info("Fear & Greed unavailable: %s", exc)
        return None
    rating = str(fg.get("rating", "")).lower()
    return {
        "value": round(float(fg["score"]), 1),
        "rating": LABELS.get(rating, rating),
        "previous_week": fg.get("previous_1_week"),
        "previous_month": fg.get("previous_1_month"),
        "spark": [round(float(p["y"]), 1) for p in history[-90:]],
    }
