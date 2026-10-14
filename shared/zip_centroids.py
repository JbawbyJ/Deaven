"""Offline ZIP centroids for listings that have a ZIP and no coordinates.

This is a small bundled table, not a geocoder and not a network call.
Unknown ZIPs return None so lat/lng stay null. Figures are approximate
public centroids for the demo catalog and tests.
"""

from __future__ import annotations

import re
from typing import Optional

# ZIP -> (lat, lng). Five-digit US codes only.
_CENTROIDS: dict[str, tuple[float, float]] = {
    "10001": (40.7506, -73.9971),
    "30303": (33.7490, -84.3880),  # Atlanta
    "78701": (30.2672, -97.7431),  # Austin
    "80202": (39.7392, -104.9903),  # Denver
    "94102": (37.7793, -122.4193),
    "97201": (45.5152, -122.6784),  # Portland
}

_DIGITS = re.compile(r"\d")


def centroid_for_zip(zip_code: Optional[str]) -> Optional[tuple[float, float]]:
    """Return (lat, lng) for a known ZIP, or None."""
    if not zip_code:
        return None
    digits = "".join(_DIGITS.findall(str(zip_code)))
    if len(digits) < 5:
        return None
    return _CENTROIDS.get(digits[:5])
