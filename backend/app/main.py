"""Stock Scout API.

Run from the backend folder:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import dashboard, macro, screener, stocks

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Stock Scout API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

for r in (dashboard.router, screener.router, stocks.router, macro.router):
    app.include_router(r)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "fred_key": bool(settings.fred_api_key),
        "sec_user_agent": bool(settings.sec_user_agent),
        "finnhub_key": bool(settings.finnhub_api_key),
    }
