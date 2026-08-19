from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_MODE", "local")
    monkeypatch.setenv("SCOUT_BACKEND", "local")
    monkeypatch.setenv("STORE_BACKEND", "local")
    monkeypatch.setenv("SEED_DEMO_DEALS", "true")
    monkeypatch.setenv("DEAVEN_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from backend.db.store import reset_local_store

    reset_local_store(tmp_path / "local_store.json", seed=True)
    yield


@pytest.fixture
def client(isolated_store):
    from fastapi.testclient import TestClient
    from backend.api.main import app

    with TestClient(app) as test_client:
        yield test_client
