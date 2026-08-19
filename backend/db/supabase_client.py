"""
Optional Supabase persistence. Imported only when STORE_BACKEND=supabase.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from supabase import Client, create_client

from shared.schemas.deal import DealPayload, DealStatus, DealTier

logger = logging.getLogger(__name__)

TABLE_NAME = "deals"
_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")

    _client = create_client(url, key)
    return _client


def _row_from_payload(payload: DealPayload) -> dict:
    return {
        "deal_id": payload.deal_id,
        "payload": payload.model_dump(mode="json"),
    }


def save_deal(payload: DealPayload) -> DealPayload:
    row = _row_from_payload(payload)
    get_client().table(TABLE_NAME).upsert(row, on_conflict="deal_id").execute()
    logger.debug("Saved deal %s to Supabase", payload.deal_id)
    return payload


def fetch_deal(deal_id: str) -> Optional[DealPayload]:
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


def _tier_value(value) -> str:
    if value is None:
        return ""
    return value.value if isinstance(value, DealTier) else str(value)


def _status_value(value) -> str:
    if value is None:
        return ""
    return value.value if isinstance(value, DealStatus) else str(value)


def list_deals(
    tier: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[DealPayload]:
    response = get_client().table(TABLE_NAME).select("payload").execute()
    rows = [DealPayload.model_validate(r["payload"]) for r in (response.data or [])]
    if tier and tier != "all":
        wanted = tier.lower()
        rows = [d for d in rows if _tier_value(d.deal_tier).lower() == wanted]
    if status:
        wanted = status.lower()
        rows = [d for d in rows if _status_value(d.status).lower() == wanted]
    rows.sort(key=lambda d: (d.deal_score is not None, d.deal_score or 0), reverse=True)
    return rows[:limit]


def pipeline_stats() -> dict:
    deals = list_deals(limit=1000)
    scores = [d.deal_score for d in deals if d.deal_score is not None]
    margins = [
        d.valuation_report.estimated_gross_margin
        for d in deals
        if d.valuation_report is not None
    ]
    tiers = [_tier_value(d.deal_tier).lower() for d in deals]
    return {
        "total_ingested": len(deals),
        "fire_deals": tiers.count("fire"),
        "strong_deals": tiers.count("strong"),
        "watchlist_deals": tiers.count("watchlist"),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "avg_margin": round(sum(margins) / len(margins), 4) if margins else 0,
    }
