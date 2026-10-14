"""
Thin adapter from a stored deal to a search hit.

Deals on main are DealPayload (shared.schemas.deal.ListingData): title, price,
mileage, year, make, model, and a free-text location. Builder is publishing
the listing schema on agent/builder/deaven-ingestion. That branch is not on
main yet. When it lands, update this module only.

Coordinates are read from the listing when present (latitude/longitude,
lat/lng, or lat/lon). Otherwise the location string is resolved with the
fixture gazetteer.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.search.geo import haversine_miles, resolve_place
from shared.schemas.search import SearchHit

_LAT_FIELDS = ("latitude", "lat")
_LNG_FIELDS = ("longitude", "lng", "lon")


def to_hit(payload: Any, center: Optional[tuple[float, float]] = None) -> SearchHit:
    listing = payload.listing
    lat, lng, geo_source = _coordinates(listing)
    distance = None
    if center is not None and lat is not None and lng is not None:
        distance = round(haversine_miles(center[0], center[1], lat, lng), 1)

    return SearchHit(
        deal_id=str(payload.deal_id),
        title=_text(listing, "title") or "Untitled",
        price=float(_field(listing, "price") or 0),
        year=_optional_int(_field(listing, "year")),
        make=_text(listing, "make"),
        model=_text(listing, "model"),
        mileage=_optional_int(_field(listing, "mileage")),
        location=_text(listing, "location"),
        lat=lat,
        lng=lng,
        geo_source=geo_source,
        distance_miles=distance,
        deal_score=getattr(payload, "deal_score", None),
        deal_tier=_enum_str(getattr(payload, "deal_tier", None)),
    )


def _coordinates(listing: Any) -> tuple[Optional[float], Optional[float], Optional[str]]:
    lat = _optional_float(_field(listing, *_LAT_FIELDS))
    lng = _optional_float(_field(listing, *_LNG_FIELDS))
    if lat is not None and lng is not None:
        return lat, lng, "listing"
    resolved = resolve_place(_text(listing, "location"))
    if resolved is None:
        return None, None, None
    _label, place_lat, place_lng, _how = resolved
    return place_lat, place_lng, "fixture_gazetteer"


def _field(listing: Any, *names: str) -> Any:
    extra = getattr(listing, "model_extra", None) or {}
    data = listing if isinstance(listing, dict) else {}
    for name in names:
        if name in data and data[name] not in (None, ""):
            return data[name]
        if isinstance(extra, dict) and extra.get(name) not in (None, ""):
            return extra[name]
        value = getattr(listing, name, None)
        if value not in (None, ""):
            return value
    return None


def _text(listing: Any, name: str) -> Optional[str]:
    value = _field(listing, name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    number = _optional_float(value)
    if number is None:
        return None
    return int(number)


def _enum_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)
