"""
Local-first settings. Production keys are optional; missing values
keep the API on the in-process JSON store and heuristic pipeline.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent

load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_REPO_ROOT / ".env", override=False)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or default).strip()


def pipeline_mode() -> str:
    """local = heuristic scoring (no LLM/scraper keys). full = live agents."""
    return _env("PIPELINE_MODE", "local").lower()


def scout_backend() -> str:
    """local = catalog fixtures. live = Playwright/eBay/etc scrapers."""
    return _env("SCOUT_BACKEND", "local").lower()


def scout_scheduler_enabled() -> bool:
    """Background scout loop. Default off so TestClient/lifespan cannot hang."""
    return _env("SCOUT_SCHEDULER", "").lower() in {"1", "true", "yes", "on"}


def alert_webhook_url() -> str:
    return _env("ALERT_WEBHOOK_URL")


def store_backend() -> str:
    """local = JSON file. supabase = remote deals table."""
    configured = _env("STORE_BACKEND", "local").lower()
    if configured == "supabase":
        return "supabase"
    return "local"


def seed_demo_deals() -> bool:
    return _env("SEED_DEMO_DEALS", "true").lower() in {"1", "true", "yes", "on"}


def data_dir() -> Path:
    raw = _env("DEAVEN_DATA_DIR")
    path = Path(raw) if raw else _BACKEND_DIR / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_path() -> Path:
    return data_dir() / "local_store.json"


def cors_origins() -> list[str]:
    raw = _env(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def supabase_configured() -> bool:
    return bool(_env("SUPABASE_URL") and _env("SUPABASE_KEY"))
