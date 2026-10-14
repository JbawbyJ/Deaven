"""Distance helpers for area search. Not a geocoder."""

from __future__ import annotations

import math
import re
from typing import Optional

EARTH_RADIUS_MILES = 3958.8

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def parse_coordinates(text: Optional[str]) -> Optional[tuple[float, float]]:
    """Parse a 'lat,lng' string. Returns None when it is not a coordinate pair."""
    if text is None:
        return None
    match = _COORD_RE.match(str(text).strip())
    if match is None:
        return None
    lat = float(match.group(1))
    lng = float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng
