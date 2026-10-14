"""
Fixture city centroids and distance.

Listings store a city string, not coordinates. Area search resolves known
labels here until ingestion persists latitude/longitude. This is not a geocoder.
"""

from __future__ import annotations

import math
import re
from typing import Optional

EARTH_RADIUS_MILES = 3958.8

# Catalog cities first, then a few origins so a radius query is usable.
_PLACES: tuple[tuple[str, float, float], ...] = (
    ("Austin, TX", 30.2672, -97.7431),
    ("Portland, OR", 45.5152, -122.6784),
    ("Denver, CO", 39.7392, -104.9903),
    ("Atlanta, GA", 33.7490, -84.3880),
    ("Japan", 35.6762, 139.6503),
    ("Dallas, TX", 32.7767, -96.7970),
    ("Houston, TX", 29.7604, -95.3698),
    ("Los Angeles, CA", 34.0522, -118.2437),
    ("Chicago, IL", 41.8781, -87.6298),
    ("New York, NY", 40.7128, -74.0060),
    ("Seattle, WA", 47.6062, -122.3321),
    ("Miami, FL", 25.7617, -80.1918),
)

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace(".", " ").replace(",", " ").split())


def _index() -> dict[str, tuple[str, float, float]]:
    index: dict[str, tuple[str, float, float]] = {}
    cities: dict[str, list[tuple[str, float, float]]] = {}
    for label, lat, lng in _PLACES:
        key = _normalize(label)
        index[key] = (label, lat, lng)
        parts = key.split()
        city = " ".join(parts[:-1]) if len(parts) >= 2 and len(parts[-1]) == 2 else key
        cities.setdefault(city, []).append((label, lat, lng))
    for city, rows in cities.items():
        if len(rows) == 1 and city not in index:
            index[city] = rows[0]
    return index


_INDEX = _index()


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def resolve_place(text: Optional[str]) -> Optional[tuple[str, float, float, str]]:
    """Return (label, lat, lng, resolved_by) or None."""
    if text is None or not str(text).strip():
        return None
    raw = str(text).strip()
    match = _COORD_RE.match(raw)
    if match:
        lat = float(match.group(1))
        lng = float(match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None
        return (f"{lat:.4f}, {lng:.4f}", lat, lng, "coordinates")
    found = _INDEX.get(_normalize(raw))
    if found is None:
        return None
    label, lat, lng = found
    return (label, lat, lng, "fixture_gazetteer")


def place_options() -> list[dict]:
    return [{"label": label, "lat": lat, "lng": lng} for label, lat, lng in _PLACES]
