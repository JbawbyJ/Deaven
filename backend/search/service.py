"""Filter stored deals by area and the listing fields search can query today."""

from __future__ import annotations

from typing import Optional

from backend.db.client import list_deals
from backend.search.adapter import to_hit
from backend.search.geo import place_options, resolve_place
from shared.schemas.search import SearchCenter, SearchHit, SearchResponse

FIXTURE_NOTE = (
    "Map coordinates come from a fixture city gazetteer until ingestion "
    "stores latitude and longitude on the listing."
)

_MAX_SCAN = 1000


class UnresolvedLocation(Exception):
    def __init__(self, location: str):
        self.location = location
        super().__init__(location)


def search_deals(
    *,
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_miles: float = 250,
    make: Optional[str] = None,
    model: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    mileage_max: Optional[int] = None,
    limit: int = 100,
) -> SearchResponse:
    center = _center(location, lat, lng)
    center_pair = (center.lat, center.lng) if center else None
    hits = [to_hit(deal, center_pair) for deal in list_deals(limit=_MAX_SCAN)]

    matched = []
    for hit in hits:
        if center is not None:
            if hit.distance_miles is None or hit.distance_miles > radius_miles:
                continue
        if not _matches(hit, make, model, year_min, year_max, price_min, price_max, mileage_max):
            continue
        matched.append(hit)

    matched.sort(key=lambda hit: _sort_key(hit, center is not None))
    return SearchResponse(
        center=center,
        radius_miles=radius_miles if center is not None else None,
        total=len(matched),
        listings=matched[:limit],
        note=FIXTURE_NOTE,
    )


def places() -> list[dict]:
    return place_options()


def _center(
    location: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
) -> Optional[SearchCenter]:
    if lat is not None or lng is not None:
        if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise UnresolvedLocation(location or "lat/lng")
        label = location.strip() if location and location.strip() else f"{lat:.4f}, {lng:.4f}"
        return SearchCenter(lat=lat, lng=lng, label=label, resolved_by="coordinates")
    if location is None or not location.strip():
        return None
    resolved = resolve_place(location)
    if resolved is None:
        raise UnresolvedLocation(location.strip())
    label, place_lat, place_lng, resolved_by = resolved
    return SearchCenter(lat=place_lat, lng=place_lng, label=label, resolved_by=resolved_by)


def _matches(
    hit: SearchHit,
    make: Optional[str],
    model: Optional[str],
    year_min: Optional[int],
    year_max: Optional[int],
    price_min: Optional[float],
    price_max: Optional[float],
    mileage_max: Optional[int],
) -> bool:
    if make and (not hit.make or hit.make.strip().lower() != make.strip().lower()):
        return False
    if model and (not hit.model or model.strip().lower() not in hit.model.strip().lower()):
        return False
    if year_min is not None and (hit.year is None or hit.year < year_min):
        return False
    if year_max is not None and (hit.year is None or hit.year > year_max):
        return False
    if price_min is not None and hit.price < price_min:
        return False
    if price_max is not None and hit.price > price_max:
        return False
    if mileage_max is not None and (hit.mileage is None or hit.mileage > mileage_max):
        return False
    return True


def _sort_key(hit: SearchHit, has_center: bool):
    if has_center:
        return (hit.distance_miles if hit.distance_miles is not None else 10**9, hit.price, hit.deal_id)
    return (hit.price, hit.deal_id)
