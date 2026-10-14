"""Thin adapter for the listing model on draft PR #8.

PR #8 (`agent/beebc-grok/listing-model` @ 5bc43fe) is not merged here, and this
lane does not edit `shared/`. When `shared.vin.vin_key` and
`shared.schemas.market.vehicle_key_for` can be imported, those functions are
used. Otherwise the same rules run locally:

- `vin_key(raw: str) -> str | None` is the normalized VIN, or None.
- `vehicle_key` is that VIN, or the sha256 of year, make, model, trim,
  10,000-mile mileage band, and the ZIP parsed from `location.label`.

`ListingLocation` has no zip field. The ZIP inside `vehicle_key` is the one
PR #8 reads out of the label. Comp distance uses latitude and longitude.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

_MILEAGE_BAND = 10_000
_ZIP = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
_SEPARATORS = re.compile(r"[\s-]+")

_TRANSLIT: dict[str, int] = {
    **{str(digit): digit for digit in range(10)},
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_WEIGHTS: tuple[int, ...] = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def vin_key(raw: str) -> str | None:
    """Normalized VIN, or None when the value is missing or fails the check digit."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    shared = _shared_vin_key()
    if shared is not None:
        return shared(raw)
    return _vin_key_fallback(raw)


def mileage_band(mileage: int | None) -> str:
    """10,000-mile bands. None stays an explicit unknown band."""
    if mileage is None:
        return "unknown"
    start = (int(mileage) // _MILEAGE_BAND) * _MILEAGE_BAND
    return f"{start}-{start + _MILEAGE_BAND - 1}"


def postal_code(location: Any) -> str:
    """ZIP from the location label. ListingLocation has no zip field."""
    label = _loc_get(location, "label")
    if not label:
        return ""
    match = _ZIP.search(str(label))
    return match.group(1) if match else ""


def fuzzy_vehicle_key(
    *,
    year: int,
    make: str,
    model: str,
    trim: str | None,
    mileage: int | None,
    location: Any,
) -> str:
    """sha256 of year, make, model, trim, mileage band, and zip-from-label."""
    shared = _shared_fuzzy_vehicle_key()
    if shared is not None:
        return shared(
            year=year,
            make=make,
            model=model,
            trim=trim,
            mileage=mileage,
            location=_as_location(location),
        )
    payload = "|".join(
        [
            str(year),
            _token(make),
            _token(model),
            _token(trim),
            mileage_band(mileage),
            postal_code(location),
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def vehicle_key_for(
    *,
    vin: str | None,
    year: int,
    make: str,
    model: str,
    trim: str | None,
    mileage: int | None,
    location: Any,
) -> str:
    """vin_key when it returns a VIN. Missing or invalid VINs use the fuzzy hash."""
    shared = _shared_vehicle_key_for()
    if shared is not None:
        return shared(
            vin=vin,
            year=year,
            make=make,
            model=model,
            trim=trim,
            mileage=mileage,
            location=_as_location(location),
        )
    if isinstance(vin, str) and vin.strip():
        key = vin_key(vin)
        if key is not None:
            return key
    return fuzzy_vehicle_key(
        year=year,
        make=make,
        model=model,
        trim=trim,
        mileage=mileage,
        location=location,
    )


def vehicle_key(listing: Any) -> str:
    """vehicle_key for a NormalizedListing-shaped record or a plain dict."""
    shared = _shared_vehicle_key()
    if shared is not None and _looks_like_normalized(listing):
        try:
            return shared(listing)
        except (TypeError, ValueError, AttributeError):
            pass
    return vehicle_key_for(
        vin=_field(listing, "vin"),
        year=_field(listing, "year"),
        make=_field(listing, "make") or "",
        model=_field(listing, "model") or "",
        trim=_field(listing, "trim"),
        mileage=_field(listing, "mileage"),
        location=_field(listing, "location"),
    )


@dataclass(frozen=True)
class ListingView:
    """Fields pricing reads off a NormalizedListing, ListingFacts, or fixture dict."""

    listing_id: str
    price: float
    make: str | None
    model: str | None
    trim: str | None
    year: int | None
    mileage: int | None
    region: str | None
    vin: str | None
    label: str | None
    latitude: float | None
    longitude: float | None
    currency: str | None
    source: str | None
    first_seen: datetime | None
    last_seen: datetime | None
    vehicle_key: str
    input_index: int


@dataclass(frozen=True)
class PriceView:
    """One PriceObservation: listing_id, observed_at, amount, currency, kind."""

    listing_id: str
    observed_at: datetime
    amount: float
    currency: str
    kind: str


def read_listing(record: Any, index: int = 0) -> ListingView | None:
    """Adapt one listing. Non-USD and non-positive prices are omitted."""
    if _is_price_observation(record):
        return None
    currency = _currency(_field(record, "currency"))
    if currency is not None and currency != "USD":
        return None
    price = _field(record, "price")
    if price is None:
        price = _field(record, "amount")
    try:
        amount = float(price)
    except (TypeError, ValueError):
        return None
    if amount <= 0 or amount != amount or amount == float("inf"):
        return None

    location = _field(record, "location")
    region = _loc_get(location, "region")
    if region is None:
        region = _field(record, "region")
    vin = _field(record, "vin")
    year = _field(record, "year")
    if year is not None:
        year = int(year)
    mileage = _field(record, "mileage")
    if mileage is not None:
        mileage = int(mileage)
    key_vin = vin if isinstance(vin, str) else None
    if vin_key(key_vin or "") is None and year is None:
        return None
    identity = vehicle_key_for(
        vin=key_vin,
        year=year if year is not None else 0,
        make=_field(record, "make") or "",
        model=_field(record, "model") or "",
        trim=_field(record, "trim"),
        mileage=mileage,
        location=location if location is not None else SimpleNamespace(label=None),
    )
    return ListingView(
        listing_id=_listing_id(record),
        price=amount,
        make=_field(record, "make"),
        model=_field(record, "model"),
        trim=_field(record, "trim"),
        year=year,
        mileage=mileage,
        region=_text(region),
        vin=key_vin,
        label=_text(_loc_get(location, "label")),
        latitude=_float_or_none(_loc_get(location, "latitude")),
        longitude=_float_or_none(_loc_get(location, "longitude")),
        currency=currency or "USD",
        source=_text(_field(record, "source")),
        first_seen=_parse_dt(_field(record, "first_seen")),
        last_seen=_parse_dt(_field(record, "last_seen")),
        vehicle_key=identity,
        input_index=index,
    )


def read_price(record: Any) -> PriceView | None:
    """Adapt one PriceObservation. Non-USD rows are omitted."""
    currency = _currency(_field(record, "currency")) or "USD"
    if currency != "USD":
        return None
    listing_id = _field(record, "listing_id")
    observed_at = _parse_dt(_field(record, "observed_at"))
    if not listing_id or observed_at is None:
        return None
    try:
        amount = float(_field(record, "amount"))
    except (TypeError, ValueError):
        return None
    if amount < 0 or amount != amount or amount == float("inf"):
        return None
    kind = _field(record, "kind") or "asking"
    if hasattr(kind, "value"):
        kind = kind.value
    return PriceView(
        listing_id=str(listing_id).strip(),
        observed_at=observed_at,
        amount=amount,
        currency=currency,
        kind=str(kind).strip().lower(),
    )


def _listing_id(record: Any) -> str:
    existing = _field(record, "observation_id") or _field(record, "listing_id")
    if existing:
        return str(existing).strip()
    source = _field(record, "source") or ""
    url = _field(record, "source_url") or _field(record, "url") or ""
    if source or url:
        return hashlib.sha256(f"{source}\n{url}".encode()).hexdigest()[:16]
    return ""


def _field(record: Any, name: str) -> Any:
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def _loc_get(location: Any, name: str) -> Any:
    if location is None:
        return None
    if isinstance(location, dict):
        return location.get(name)
    return getattr(location, name, None)


def _as_location(location: Any) -> Any:
    if isinstance(location, dict):
        return SimpleNamespace(
            label=location.get("label"),
            city=location.get("city"),
            region=location.get("region"),
            country=location.get("country"),
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
        )
    if location is None:
        return SimpleNamespace(label=None)
    return location


def _looks_like_normalized(listing: Any) -> bool:
    return not isinstance(listing, dict) and hasattr(listing, "location") and hasattr(listing, "source_url")


def _is_price_observation(record: Any) -> bool:
    has_amount = _field(record, "amount") is not None
    has_kind = _field(record, "kind") is not None
    has_vehicle = _field(record, "make") is not None or _field(record, "model") is not None
    return bool(has_amount and has_kind and not has_vehicle)


def _token(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().casefold().split())


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _currency(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    text = str(value).strip().upper()
    return text or None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _shared_vin_key():
    try:
        from shared.vin import vin_key as shared
    except ImportError:
        return None
    return shared


def _shared_vehicle_key_for():
    try:
        from shared.schemas.market import vehicle_key_for as shared
    except ImportError:
        return None
    return shared


def _shared_fuzzy_vehicle_key():
    try:
        from shared.schemas.market import fuzzy_vehicle_key as shared
    except ImportError:
        return None
    return shared


def _shared_vehicle_key():
    try:
        from shared.schemas.market import vehicle_key as shared
    except ImportError:
        return None
    return shared


def _vin_key_fallback(raw: str) -> str | None:
    vin = _SEPARATORS.sub("", raw).upper()
    if len(vin) != 17 or any(char not in _TRANSLIT for char in vin):
        return None
    total = sum(_TRANSLIT[char] * weight for char, weight in zip(vin, _WEIGHTS))
    remainder = total % 11
    expected = "X" if remainder == 10 else str(remainder)
    if vin[8] != expected:
        return None
    return vin
