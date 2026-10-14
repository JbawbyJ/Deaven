"""
Thin adapter from a stored deal to a search hit.

Reads ListingData as extended on agent/builder/deaven-ingestion (PR #3):
`listing_id`, `region`, `zip`, and optional `lat`/`lng`. Ingestion fills
coordinates from the listing or from a ZIP centroid. This module does not
invent a pin from the city name.

`listing_id` is the stable id. `deal_id` stays the pipeline id so the
current deal page still opens.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.search.geo import haversine_miles
from shared.schemas.search import SearchHit


def to_hit(payload: Any, center: Optional[tuple[float, float]] = None) -> SearchHit:
    listing = payload.listing
    lat, lng = _coordinates(listing)
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
        distance_miles=distance,
        deal_score=getattr(payload, "deal_score", None),
        deal_tier=_enum_str(getattr(payload, "deal_tier", None)),
    )


def _coordinates(listing: Any) -> tuple[Optional[float], Optional[float]]:
    lat = _optional_float(_field(listing, "lat"))
    lng = _optional_float(_field(listing, "lng"))
    if lat is None or lng is None:
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, None
    return lat, lng


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
