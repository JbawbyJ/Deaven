"""Database access — Supabase client and deal persistence."""

from backend.db.client import fetch_deal, get_client, save_deal

__all__ = ["fetch_deal", "get_client", "save_deal"]
