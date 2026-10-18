"""Response models for area search. Not a second listing schema."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SearchHit(BaseModel):
    # Stable ingestion id (`{source}:{source_id}`). Null until that field is set.
    listing_id: Optional[str] = None
    # Pipeline id. Opens the existing /deals/{deal_id} page.
    deal_id: str
    title: str
    price: float
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    mileage: Optional[int] = None
    location: Optional[str] = None
    region: Optional[str] = None
    zip: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    distance_miles: Optional[float] = None
    deal_score: Optional[float] = None
    deal_tier: Optional[str] = None


class SearchCenter(BaseModel):
    lat: float
    lng: float
    label: str


class SearchResponse(BaseModel):
    center: Optional[SearchCenter] = None
    radius_miles: Optional[float] = None
    total: int
    listings: list[SearchHit]
    without_coordinates: int = 0
    note: str
