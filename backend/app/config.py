"""Settings read from backend/.env (see .env.example at the repo root)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    fred_api_key: str = os.getenv("FRED_API_KEY", "")
    sec_user_agent: str = os.getenv("SEC_USER_AGENT", "")
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        ]
    )
    data_dir: Path = BACKEND_DIR / "data"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
