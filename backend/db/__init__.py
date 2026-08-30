"""Database access — local JSON store, optional Supabase."""

from backend.db.client import (
    delete_watchlist,
    fetch_deal,
    find_deal_by_url,
    get_client,
    get_watchlist,
    list_deals,
    list_watchlists,
    pipeline_stats,
    save_deal,
    save_watchlist,
)

__all__ = [
    "delete_watchlist",
    "fetch_deal",
    "find_deal_by_url",
    "get_client",
    "get_watchlist",
    "list_deals",
    "list_watchlists",
    "pipeline_stats",
    "save_deal",
    "save_watchlist",
]
