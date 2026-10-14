"""Dependency-light VIN normalization and offline decode.

Import this package from scrapers, dedupe, and valuation. Nothing here
requires an API key.

    normalize_vin(raw) -> str | None
    validate_check_digit(raw) -> bool | None   # informational; not a hard reject
    decode_vin(raw, *, as_of=None) -> VinDecode | None
    vin_key(raw) -> str | None                 # canonical VIN, for dedupe
    decode_vpic(raw, *, enabled=None, timeout=5.0) -> dict | None

`decode_vpic` calls the public NHTSA vPIC API only when `enabled` is true or
`VIN_VPIC_ENABLED` is set. It times out, returns None on failure, and caches
successful responses in memory.
"""

from shared.vin.core import (
    VinDecode,
    decode_vin,
    expected_check_digit,
    normalize_vin,
    validate_check_digit,
    vin_key,
)
from shared.vin.vpic import clear_vpic_cache, decode_vpic, vpic_enabled

__all__ = [
    "VinDecode",
    "clear_vpic_cache",
    "decode_vin",
    "decode_vpic",
    "expected_check_digit",
    "normalize_vin",
    "validate_check_digit",
    "vin_key",
    "vpic_enabled",
]
