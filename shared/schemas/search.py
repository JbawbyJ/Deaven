"""Response models for area search. Not a second listing schema."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


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
    geo_source: Optional[Literal["listing", "fixture_gazetteer"]] = None
    distance_miles: Optional[float] = None
    deal_score: Optional[float] = None
    deal_tier: Optional[str] = None


class SearchCenter(BaseModel):
    lat: float
    lng: float
    label: str
    resolved_by: Literal["coordinates", "fixture_gazetteer"]


class SearchResponse(BaseModel):
    center: Optional[SearchCenter] = None
    radius_miles: Optional[float] = None
    total: int
    listings: list[SearchHit]
    note: str


class PlaceOption(BaseModel):
    label: str
    lat: float
    lng: float


class PlacesResponse(BaseModel):
    source: Literal["fixture_gazetteer"] = "fixture_gazetteer"
    note: str
    places: list[PlaceOption] = Field(default_factory=list)
