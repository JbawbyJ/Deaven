"""
Deal persistence.

Default: local JSON store (no Supabase keys).
Optional: set STORE_BACKEND=supabase plus SUPABASE_URL/SUPABASE_KEY.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.core.settings import store_backend, supabase_configured
from shared.schemas.deal import DealPayload, WatchlistFilter

logger = logging.getLogger(__name__)

TABLE_NAME = "deals"


def _use_supabase() -> bool:
    return store_backend() == "supabase" and supabase_configured()


def get_client():
    """Return a cached Supabase client. Raises if keys are missing."""
    if not supabase_configured():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set to use STORE_BACKEND=supabase."
        )

    from backend.db import supabase_client

    return supabase_client.get_client()


def save_deal(payload: DealPayload) -> DealPayload:
    if _use_supabase():
        from backend.db import supabase_client

        return supabase_client.save_deal(payload)
    from backend.db.store import get_local_store

    return get_local_store().save_deal(payload)


def fetch_deal(deal_id: str) -> Optional[DealPayload]:
    if _use_supabase():
        from backend.db import supabase_client

        return supabase_client.fetch_deal(deal_id)
    from backend.db.store import get_local_store

    return get_local_store().get_deal(deal_id)


def find_deal_by_url(url: str) -> Optional[DealPayload]:
    if _use_supabase():
        return None
    from backend.db.store import get_local_store

    return get_local_store().find_by_url(url)


def list_deals(
    tier: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[DealPayload]:
    if _use_supabase():
        from backend.db import supabase_client

        return supabase_client.list_deals(tier=tier, status=status, limit=limit)
    from backend.db.store import get_local_store

    return get_local_store().list_deals(tier=tier, status=status, limit=limit)


def pipeline_stats() -> dict:
    if _use_supabase():
        from backend.db import supabase_client

        return supabase_client.pipeline_stats()
    from backend.db.store import get_local_store

    return get_local_store().pipeline_stats()


def list_watchlists() -> list[WatchlistFilter]:
    if _use_supabase():
        return []
    from backend.db.store import get_local_store

    return get_local_store().list_watchlists()


def save_watchlist(item: WatchlistFilter) -> WatchlistFilter:
    if _use_supabase():
        return item
    from backend.db.store import get_local_store

    return get_local_store().save_watchlist(item)


def delete_watchlist(filter_id: str) -> bool:
    if _use_supabase():
        return False
    from backend.db.store import get_local_store

    return get_local_store().delete_watchlist(filter_id)


get_deal = fetch_deal
