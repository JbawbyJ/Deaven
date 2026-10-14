from __future__ import annotations

import sys
from functools import partial
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
    monkeypatch.delenv("SCOUT_SCHEDULER", raising=False)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)

    from backend.db.store import reset_local_store

    reset_local_store(tmp_path / "local_store.json", seed=True)
    yield


class _SyncASGIClient:
    """Sync facade over httpx.AsyncClient. Starlette's TestClient warns without httpx2."""

    def __init__(self, portal, client) -> None:
        self._portal = portal
        self._client = client

    def _call(self, method: str, url: str, **kwargs):
        return self._portal.call(partial(getattr(self._client, method), url, **kwargs))

    def get(self, url: str, **kwargs):
        return self._call("get", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._call("post", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self._call("patch", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self._call("delete", url, **kwargs)


@pytest.fixture
def client(isolated_store):
    import anyio
    import httpx

    from backend.api.main import app

    lifespan = app.router.lifespan_context(app)
    transport = httpx.ASGITransport(app=app)
    with anyio.from_thread.start_blocking_portal() as portal:
        portal.call(lifespan.__aenter__)
        http = httpx.AsyncClient(transport=transport, base_url="http://testserver")
        portal.call(http.__aenter__)
        try:
            yield _SyncASGIClient(portal, http)
        finally:
            portal.call(http.__aexit__, None, None, None)
            portal.call(lifespan.__aexit__, None, None, None)
