"""Area search over stored listings. Does not change /deals."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.search.service import UnresolvedLocation, search_deals
from shared.schemas.search import SearchResponse

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
    region: Optional[str] = None,
    zip: Optional[str] = None,
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
            region=region,
            zip_code=zip,
            limit=limit,
        )
    except UnresolvedLocation as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not resolve location '{exc.location}'. "
                "Pass lat and lng or a 'lat,lng' pair. A ZIP or a region code "
                "such as 'TX' filters those listing fields. City names are not geocoded."
            ),
        ) from exc
