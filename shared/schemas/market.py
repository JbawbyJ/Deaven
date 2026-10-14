"""Pricing, source, and vehicle identity on top of the ingestion listings.

NormalizedListing, ListingLocation, SellerType, and MatchMethod come from
shared.schemas.listing (PR #3). This module does not redefine them.
vin_key is shared.vin.vin_key: a normalized VIN, or None when the VIN is invalid.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.schemas.deal import DealSource
from shared.schemas.listing import ListingLocation, MatchMethod, NormalizedListing, SellerType
from shared.vin import vin_key

_ZIP = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
_MILEAGE_BAND = 10_000


class PriceKind(str, Enum):
    ASKING = "asking"
    BID = "bid"
    SOLD = "sold"
    RESERVE_NOT_MET = "reserve_not_met"


class Source(BaseModel):
    """Where a listing was seen.

    `code` reuses DealSource values (bat, ebay, ...). `kind` reuses SellerType
    (dealer, marketplace, auction). robots_ok and tos_reviewed stay false until
    someone has actually checked that source.
    """

    model_config = ConfigDict(extra="forbid")

    code: DealSource
    kind: SellerType
    name: str = Field(min_length=1)
    base_url: str
    robots_ok: bool = False
    tos_reviewed: bool = False

    @field_validator("base_url")
    @classmethod
    def _base_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an http(s) URL")
        return value.strip()


class Seller(BaseModel):
    """Named seller. seller_type is the #3 channel enum, not a new one."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    seller_type: SellerType

    @field_validator("name")
    @classmethod
    def _name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class PriceObservation(BaseModel):
    """One observed price for a NormalizedListing.observation_id."""

    model_config = ConfigDict(extra="forbid")

    listing_id: str = Field(min_length=1)
    observed_at: datetime
    amount: float = Field(ge=0)
    currency: str = "USD"
    kind: PriceKind

    @field_validator("observed_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return code

    @field_validator("amount")
    @classmethod
    def _finite(cls, value: float) -> float:
        if value != value or value == float("inf"):
            raise ValueError("amount must be finite")
        return float(value)


class VehicleCluster(BaseModel):
    """Listings that share a vehicle_key. match_method is vin or fuzzy."""

    model_config = ConfigDict(extra="forbid")

    vehicle_key: str = Field(min_length=1)
    listing_ids: list[str] = Field(min_length=1)
    match_method: MatchMethod

    @field_validator("listing_ids")
    @classmethod
    def _ids(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("listing_ids must not be blank")
        return cleaned

    @field_validator("match_method")
    @classmethod
    def _vin_or_fuzzy(cls, value: MatchMethod) -> MatchMethod:
        if value is MatchMethod.SINGLETON:
            raise ValueError("match_method must be vin or fuzzy")
        return value


class _SourceMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SellerType
    name: str
    base_url: str


_CATALOG: dict[DealSource, _SourceMeta] = {
    DealSource.BRING_A_TRAILER: _SourceMeta(
        kind=SellerType.AUCTION, name="Bring a Trailer", base_url="https://bringatrailer.com"
    ),
    DealSource.CARS_AND_BIDS: _SourceMeta(
        kind=SellerType.AUCTION, name="Cars and Bids", base_url="https://carsandbids.com"
    ),
    DealSource.EBAY: _SourceMeta(
        kind=SellerType.MARKETPLACE, name="eBay", base_url="https://www.ebay.com"
    ),
    DealSource.CLASSIC_COM: _SourceMeta(
        kind=SellerType.MARKETPLACE, name="Classic.com", base_url="https://www.classic.com"
    ),
    DealSource.TCV: _SourceMeta(
        kind=SellerType.AUCTION, name="TCV", base_url="https://www.tc-v.com"
    ),
    DealSource.FACEBOOK: _SourceMeta(
        kind=SellerType.MARKETPLACE,
        name="Facebook Marketplace",
        base_url="https://www.facebook.com/marketplace",
    ),
    DealSource.AUTOTRADER: _SourceMeta(
        kind=SellerType.DEALER, name="Autotrader", base_url="https://www.autotrader.com"
    ),
    DealSource.HEMMINGS: _SourceMeta(
        kind=SellerType.MARKETPLACE, name="Hemmings", base_url="https://www.hemmings.com"
    ),
    DealSource.CRAIGSLIST: _SourceMeta(
        kind=SellerType.MARKETPLACE, name="Craigslist", base_url="https://www.craigslist.org"
    ),
    DealSource.MANUAL: _SourceMeta(
        kind=SellerType.MARKETPLACE, name="Manual", base_url="https://example.com/manual"
    ),
}


def source_for(code: DealSource | str) -> Source:
    """Catalog entry for a DealSource value. Crawl flags stay false."""
    deal_source = code if isinstance(code, DealSource) else DealSource(str(code))
    meta = _CATALOG[deal_source]
    return Source(
        code=deal_source,
        kind=meta.kind,
        name=meta.name,
        base_url=meta.base_url,
        robots_ok=False,
        tos_reviewed=False,
    )


def _token(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().casefold().split())


def mileage_band(mileage: int | None) -> str:
    """10,000-mile bands. None stays an explicit unknown band."""
    if mileage is None:
        return "unknown"
    start = (mileage // _MILEAGE_BAND) * _MILEAGE_BAND
    return f"{start}-{start + _MILEAGE_BAND - 1}"


def postal_code(location: ListingLocation) -> str:
    """ZIP from the location label. ListingLocation has no zip field."""
    if not location.label:
        return ""
    match = _ZIP.search(location.label)
    return match.group(1) if match else ""


def fuzzy_vehicle_key(
    *,
    year: int,
    make: str,
    model: str,
    trim: str | None,
    mileage: int | None,
    location: ListingLocation,
) -> str:
    """Stable sha256 of year, make, model, trim, mileage band, and zip."""
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
    location: ListingLocation,
) -> str:
    """vin_key when it returns a VIN. None (missing or invalid) uses the fuzzy hash."""
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


def vehicle_key(listing: NormalizedListing) -> str:
    return vehicle_key_for(
        vin=listing.vin,
        year=listing.year,
        make=listing.make,
        model=listing.model,
        trim=listing.trim,
        mileage=listing.mileage,
        location=listing.location,
    )
