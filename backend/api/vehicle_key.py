"""vehicle_key for the search fixture.

Mirrors PR #8 @ 5bc43fe (shared/schemas/market.py + shared/vin.vin_key).
This module is search glue. It does not replace shared/vin or shared/schemas.
ListingLocation has no zip field; the ZIP is read from the label.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

_TRANSLIT = {
    **{str(digit): digit for digit in range(10)},
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
_SEPARATORS = re.compile(r"[\s-]+")
_ZIP = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
_MILEAGE_BAND = 10_000


def vin_key(raw: Optional[str]) -> Optional[str]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    vin = _SEPARATORS.sub("", raw).upper()
    if len(vin) != 17 or any(char not in _TRANSLIT for char in vin):
        return None
    total = sum(_TRANSLIT[char] * weight for char, weight in zip(vin, _WEIGHTS))
    remainder = total % 11
    expected = "X" if remainder == 10 else str(remainder)
    if vin[8] != expected:
        return None
    return vin


def mileage_band(mileage: Optional[int]) -> str:
    if mileage is None:
        return "unknown"
    start = (mileage // _MILEAGE_BAND) * _MILEAGE_BAND
    return f"{start}-{start + _MILEAGE_BAND - 1}"


def postal_code(label: Optional[str]) -> str:
    if not label:
        return ""
    match = _ZIP.search(label)
    return match.group(1) if match else ""


def _token(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(value.strip().casefold().split())


def fuzzy_vehicle_key(
    *,
    year: int,
    make: str,
    model: str,
    trim: Optional[str],
    mileage: Optional[int],
    label: Optional[str],
) -> str:
    payload = "|".join(
        [
            str(year),
            _token(make),
            _token(model),
            _token(trim),
            mileage_band(mileage),
            postal_code(label),
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def vehicle_key_for(
    *,
    vin: Optional[str],
    year: int,
    make: str,
    model: str,
    trim: Optional[str],
    mileage: Optional[int],
    label: Optional[str],
) -> str:
    if isinstance(vin, str) and vin.strip():
        key = vin_key(vin)
        if key is not None:
            return key
    return fuzzy_vehicle_key(
        year=year, make=make, model=model, trim=trim, mileage=mileage, label=label
    )


def observation_id(source: str, source_url: str) -> str:
    return hashlib.sha256(f"{source}\n{source_url}".encode()).hexdigest()[:16]
