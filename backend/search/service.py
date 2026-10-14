"""Filter stored deals by area and the listing fields search can query today."""

from __future__ import annotations

import re
from typing import Optional

from backend.db.client import list_deals
from backend.search.adapter import to_hit
from backend.search.geo import place_options, resolve_place
from shared.schemas.search import SearchCenter, SearchHit, SearchResponse

FIXTURE_NOTE = (
    "Pins use listing coordinates when they exist. "
    "A fixture city gazetteer is only the fallback for city names."
)

_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")

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
    region: Optional[str] = None,
    zip_code: Optional[str] = None,
    limit: int = 100,
) -> SearchResponse:
    geo_location, inferred_region, inferred_zip = _read_location(location)
    center = _center(geo_location, lat, lng)
    center_pair = (center.lat, center.lng) if center else None
    region_filter = _merge(_norm_region(region), inferred_region)
    zip_filter = _merge(_norm_zip(zip_code), inferred_zip)
    hits = [to_hit(deal, center_pair) for deal in list_deals(limit=_MAX_SCAN)]

    matched = []
    for hit in hits:
        if center is not None:
            if hit.distance_miles is None or hit.distance_miles > radius_miles:
                continue
        if not _matches(
            hit,
            make,
            model,
            year_min,
            year_max,
            price_min,
            price_max,
            mileage_max,
            region_filter,
            zip_filter,
        ):
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


def _read_location(location: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Split the location box into a geo query, a region, or a ZIP.

    A 5-digit ZIP (or ZIP+4) matches `listing.zip`. A 2-letter code that is
    not a fixture city matches `listing.region`. Anything else is a place name.
    """
    if location is None or not str(location).strip():
        return None, None, None
    text = str(location).strip()
    if _ZIP_RE.fullmatch(text):
        return None, None, text
    if re.fullmatch(r"[A-Za-z]{2}", text) and resolve_place(text) is None:
        return None, text.upper(), None
    return text, None, None


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
    region: Optional[str],
    zip_code: Optional[str],
) -> bool:
    if make and (not hit.make or hit.make.strip().lower() != make.strip().lower()):
        return False
    if model and (not hit.model or model.strip().lower() not in hit.model.strip().lower()):
        return False
    if region == "":
        return False
    if region and _norm_region(hit.region) != region:
        return False
    if zip_code == "":
        return False
    if zip_code and _norm_zip(hit.zip) != zip_code:
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
    stable = hit.listing_id or hit.deal_id
    if has_center:
        return (hit.distance_miles if hit.distance_miles is not None else 10**9, hit.price, stable)
    return (hit.price, stable)


def _norm_region(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return text.casefold()


def _norm_zip(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    return str(value).strip().upper()


def _merge(explicit: Optional[str], inferred: Optional[str]) -> Optional[str]:
    """Combine two constraints. An empty string means they disagree."""
    if explicit and inferred and explicit != inferred:
        return ""
    return explicit or inferred
