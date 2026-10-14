"""Area search over stored listings. Does not change /deals."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.search.service import UnresolvedLocation, places, search_deals
from shared.schemas.search import PlacesResponse, SearchResponse

router = APIRouter(tags=["search"])


@router.get("/search/listings", response_model=SearchResponse)
async def search_listings(
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_miles: float = Query(default=250, ge=1, le=3000),
    make: Optional[str] = None,
    model: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    mileage_max: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=200),
):
    try:
        return search_deals(
            location=location,
            lat=lat,
            lng=lng,
            radius_miles=radius_miles,
            make=make,
            model=model,
            year_min=year_min,
            year_max=year_max,
            price_min=price_min,
            price_max=price_max,
            mileage_max=mileage_max,
            limit=limit,
        )
    except UnresolvedLocation as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not resolve location '{exc.location}'. "
                "Pass lat and lng, a 'lat,lng' pair, or a fixture place such as "
                "'Austin, TX'. Ingestion does not store coordinates yet."
            ),
        ) from exc


@router.get("/search/places", response_model=PlacesResponse)
async def search_places():
    return PlacesResponse(
        note="Fixture city list for the location field. Not a live geocoder.",
        places=places(),
    )
