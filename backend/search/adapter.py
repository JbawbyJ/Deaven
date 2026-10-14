"""
Thin adapter from a stored deal to a search hit.

Reads ListingData as extended on agent/builder/deaven-ingestion (PR #3):
`listing_id` (`{source}:{source_id}`), `region`, and `zip`, plus the existing
display `location`. `listing_id` is the stable id. `deal_id` stays the
pipeline id so the current deal page still opens. Older rows leave
`listing_id` null.

TODO(builder-lat-lng): remove the fixture gazetteer once ListingData stores
latitude/longitude. Coordinates already pass through when present and win
over the gazetteer.
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
        listing_id=_text(listing, "listing_id"),
        deal_id=str(payload.deal_id),
        title=_text(listing, "title") or "Untitled",
        price=float(_field(listing, "price") or 0),
        year=_optional_int(_field(listing, "year")),
        make=_text(listing, "make"),
        model=_text(listing, "model"),
        mileage=_optional_int(_field(listing, "mileage")),
        location=_text(listing, "location"),
        region=_region(_text(listing, "region")),
        zip=_text(listing, "zip"),
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
    # TODO(builder-lat-lng): delete this gazetteer fallback once lat/lng is on ListingData.
    resolved = resolve_place(_text(listing, "location"))
    if resolved is None:
        return None, None, None
    _label, place_lat, place_lng, _how = resolved
    return place_lat, place_lng, "fixture_gazetteer"


def _region(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) == 2 and value.isalpha():
        return value.upper()
    return value


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
