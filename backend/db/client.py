"""
backend/db/client.py
Supabase client for persisting DealPayload records.

Expected `deals` table (create in Supabase SQL editor):

    CREATE TABLE deals (
        deal_id TEXT PRIMARY KEY,
        payload JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

from shared.schemas.deal import DealPayload

logger = logging.getLogger(__name__)

TABLE_NAME = "deals"

_backend_dir = Path(__file__).resolve().parents[1]
load_dotenv(_backend_dir / ".env")
load_dotenv(_backend_dir.parent / ".env", override=False)

_client: Optional[Client] = None


def get_client() -> Client:
    """Return a cached Supabase client (created on first call)."""
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set in .env "
            "(see README Environment Variables)."
        )

    _client = create_client(url, key)
    return _client


def _row_from_payload(payload: DealPayload) -> dict:
    return {
        "deal_id": payload.deal_id,
        "payload": payload.model_dump(mode="json"),
    }


def save_deal(payload: DealPayload) -> DealPayload:
    """Insert or update a deal row keyed by deal_id."""
    row = _row_from_payload(payload)
    get_client().table(TABLE_NAME).upsert(row, on_conflict="deal_id").execute()
    logger.debug("Saved deal %s to Supabase", payload.deal_id)
    return payload


def fetch_deal(deal_id: str) -> Optional[DealPayload]:
    """Fetch a deal by ID, or None if not found."""
    response = (
        get_client()
        .table(TABLE_NAME)
        .select("payload")
        .eq("deal_id", deal_id)
        .maybe_single()
        .execute()
    )
    if not response.data:
        return None
    return DealPayload.model_validate(response.data["payload"])


get_deal = fetch_deal  # backwards-compatible alias
