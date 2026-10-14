"""Optional NHTSA vPIC decode. Public, keyless, off unless explicitly enabled."""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request

from shared.vin.core import normalize_vin

logger = logging.getLogger(__name__)

_VPIC_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
_CACHE: dict[str, dict] = {}
_LOCK = threading.Lock()


def vpic_enabled() -> bool:
    """True when VIN_VPIC_ENABLED is 1/true/yes/on. Default is off. No API key."""
    return os.getenv("VIN_VPIC_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def clear_vpic_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def decode_vpic(
    raw: str | None,
    *,
    enabled: bool | None = None,
    timeout: float = 5.0,
    fetch=None,
) -> dict | None:
    """Decode via NHTSA vPIC, or return None.

    `enabled=None` follows VIN_VPIC_ENABLED. Pass True to force a lookup and
    False to skip it. Timeouts, HTTP errors, and malformed payloads return None
    and are not cached. Successful payloads are cached in memory by canonical VIN.
    The request carries no credentials.
    """
    if enabled is None:
        enabled = vpic_enabled()
    if not enabled:
        return None
    vin = normalize_vin(raw)
    if vin is None:
        return None

    with _LOCK:
        cached = _CACHE.get(vin)
    if cached is not None:
        return dict(cached)

    fetcher = fetch or _fetch
    url = _VPIC_URL.format(vin=vin)
    try:
        body = fetcher(url, timeout)
        parsed = _parse(vin, body)
    except Exception:
        logger.debug("vPIC decode failed for %s", vin, exc_info=True)
        return None
    if parsed is None:
        return None
    with _LOCK:
        _CACHE[vin] = parsed
    return dict(parsed)


def _fetch(url: str, timeout: float) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "DeavenVinDecoder/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _parse(vin: str, body: str) -> dict | None:
    payload = json.loads(body)
    results = payload.get("Results") if isinstance(payload, dict) else None
    if not results or not isinstance(results, list):
        return None
    row = results[0]
    if not isinstance(row, dict):
        return None
    return {
        "vin": vin,
        "make": _text(row.get("Make")),
        "model": _text(row.get("Model")),
        "model_year": _year(row.get("ModelYear")),
        "body_class": _text(row.get("BodyClass")),
        "vehicle_type": _text(row.get("VehicleType")),
        "plant_city": _text(row.get("PlantCity")),
        "plant_country": _text(row.get("PlantCountry")),
        "error_code": _text(row.get("ErrorCode")),
        "error_text": _text(row.get("ErrorText")),
    }


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _year(value: object) -> int | None:
    text = _text(value)
    if text is not None and text.isdigit():
        return int(text)
    return None
