"""Thin HTTP entry to backend.pricing.compare. The screen posts listing ids."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db.client import fetch_deal, list_deals
from backend.pricing.compare import compare
from backend.pricing.history import PriceHistoryStore
from backend.pricing.value import facts_from_listing

router = APIRouter(tags=["compare"])

MIN_LISTINGS = 2
MAX_LISTINGS = 4
# Deal ids resolve directly. This scan only matters once a row stores listing_id.
_LISTING_SCAN_LIMIT = 1000


class CompareRequest(BaseModel):
    ids: list[str]


@router.post("/compare")
async def compare_post(body: CompareRequest):
    return _compare_ids(_clean_ids(body.ids))


@router.get("/compare")
async def compare_get(ids: str):
    return _compare_ids(_clean_ids([part.strip() for part in ids.split(",")]))


def _compare_ids(ids: list[str]) -> list[dict]:
    if len(ids) < MIN_LISTINGS or len(ids) > MAX_LISTINGS:
        raise HTTPException(status_code=400, detail="Select 2 to 4 listings.")
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="Listing ids must be unique.")

    resolved = []
    missing = []
    for listing_id in ids:
        deal = _find_deal(listing_id)
        if deal is None:
            missing.append(listing_id)
        else:
            resolved.append((listing_id, deal))
    if missing:
        raise HTTPException(
            status_code=404,
            detail="Listing not found: " + ", ".join(missing),
        )

    facts = []
    for listing_id, deal in resolved:
        try:
            facts.append(facts_from_listing(deal.listing, listing_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    history = PriceHistoryStore()
    histories = {
        item.listing_id: history.observations(item.listing_id) for item in facts
    }
    try:
        rows = compare(facts, histories=histories)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [asdict(row) for row in rows]


def _clean_ids(ids: list[str]) -> list[str]:
    cleaned = [item.strip() for item in ids]
    if any(not item for item in cleaned):
        raise HTTPException(status_code=400, detail="Listing ids must not be blank.")
    return cleaned


def _find_deal(listing_id: str):
    direct = fetch_deal(listing_id)
    if direct is not None:
        return direct
    for deal in list_deals(limit=_LISTING_SCAN_LIMIT):
        explicit = getattr(deal.listing, "listing_id", None)
        if explicit is not None and str(explicit).strip() == listing_id:
            return deal
    return None
