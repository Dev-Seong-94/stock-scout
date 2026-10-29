"""Stock Scout API.

Run from the backend folder:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import dashboard, macro, screener, stocks

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
# httpx logs every request URL at INFO, which would print API keys.
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.fred_api_key:
        threading.Thread(target=macro.warm, daemon=True).start()
    yield


app = FastAPI(title="Stock Scout API", version="0.1.0", lifespan=lifespan)
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
