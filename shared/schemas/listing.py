"""
Normalized listing contract for ingestion.

DealPayload in deal.py remains the scoring pipeline's record. This module
is the source-agnostic listing that adapters emit and dedupe merges.
Asking price is an observed listing fact. Valuation stays on ValuationReport.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shared.vin import VinError, validate_vin

MIN_MODEL_YEAR = 1886
MAX_MODEL_YEAR = 2100
MAX_MILEAGE = 2_000_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SellerType(str, Enum):
    """Channel the listing was seen on, not the private-party vs dealer flag."""

    DEALER = "dealer"
    MARKETPLACE = "marketplace"
    AUCTION = "auction"


class PhotoHashKind(str, Enum):
    CONTENT = "content"
    URL = "url"


class MatchMethod(str, Enum):
    VIN = "vin"
    FUZZY = "fuzzy"
    SINGLETON = "singleton"


class ListingLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)

    @field_validator("label", "city", "region")
    @classmethod
    def _blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("country")
    @classmethod
    def _country(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        code = value.strip().upper()
        if len(code) != 2 or not code.isalpha():
            raise ValueError("country must be an ISO 3166-1 alpha-2 code")
        return code

    @model_validator(mode="after")
    def _lat_lon_pair(self) -> "ListingLocation":
        has_lat = self.latitude is not None
        has_lon = self.longitude is not None
        if has_lat != has_lon:
            raise ValueError("latitude and longitude must be set together")
        return self


class ListingPhoto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    sha256: Optional[str] = None
    hash_kind: Optional[PhotoHashKind] = None

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        return _require_http_url(value, "photo url")

    @field_validator("sha256")
    @classmethod
    def _sha(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        digest = value.strip().lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        return digest

    @model_validator(mode="after")
    def _hash_pair(self) -> "ListingPhoto":
        if (self.sha256 is None) != (self.hash_kind is None):
            raise ValueError("sha256 and hash_kind must be set together")
        return self


class RawProvenance(BaseModel):
    """Exact payload an adapter accepted, so later lanes can audit a merge."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    source_url: str
    fetched_at: datetime
    payload: dict[str, Any]
    payload_sha256: str

    @field_validator("fetched_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @field_validator("payload_sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        digest = value.strip().lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("payload_sha256 must be 64 lowercase hex characters")
        return digest

    @field_validator("source_url")
    @classmethod
    def _source_url(cls, value: str) -> str:
        return _require_source_url(value)

    @model_validator(mode="after")
    def _hash_matches_payload(self) -> "RawProvenance":
        encoded = json.dumps(
            self.payload, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
        actual = hashlib.sha256(encoded).hexdigest()
        if actual != self.payload_sha256:
            raise ValueError("payload_sha256 does not match payload")
        return self


class NormalizedListing(BaseModel):
    """One observation of a vehicle from one source."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str = ""
    vin: Optional[str] = None
    year: int = Field(ge=MIN_MODEL_YEAR, le=MAX_MODEL_YEAR)
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    trim: Optional[str] = None
    mileage: Optional[int] = Field(default=None, ge=0, le=MAX_MILEAGE)
    price: float = Field(ge=0)
    currency: str = "USD"
    location: ListingLocation = Field(default_factory=ListingLocation)
    seller_type: SellerType
    source: str = Field(min_length=1)
    source_url: str
    title: Optional[str] = None
    photos: list[ListingPhoto] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime
    provenance: RawProvenance

    @field_validator("vin")
    @classmethod
    def _vin(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        try:
            return validate_vin(value)
        except VinError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("make", "model", "source")
    @classmethod
    def _required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("trim", "title")
    @classmethod
    def _optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return code

    @field_validator("price")
    @classmethod
    def _finite_price(cls, value: float) -> float:
        if value != value or value == float("inf"):
            raise ValueError("price must be finite")
        return float(value)

    @field_validator("source_url")
    @classmethod
    def _source_url(cls, value: str) -> str:
        return _require_source_url(value)

    @field_validator("first_seen", "last_seen")
    @classmethod
    def _seen(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @model_validator(mode="after")
    def _identity_and_order(self) -> "NormalizedListing":
        if self.last_seen < self.first_seen:
            raise ValueError("last_seen is earlier than first_seen")
        if not self.observation_id:
            digest = hashlib.sha256(f"{self.source}\n{self.source_url}".encode()).hexdigest()
            self.observation_id = digest[:16]
        return self


class CanonicalListing(BaseModel):
    """Merged vehicle. source_records keeps every contributing observation.

    match_method is vin, fuzzy, or singleton. seller_type and price are taken
    from the latest observation; they are not a valuation.
    """

    model_config = ConfigDict(extra="forbid")

    canonical_id: str = Field(min_length=1)
    match_method: MatchMethod
    vin: Optional[str] = None
    year: int = Field(ge=MIN_MODEL_YEAR, le=MAX_MODEL_YEAR)
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    trim: Optional[str] = None
    mileage: Optional[int] = Field(default=None, ge=0, le=MAX_MILEAGE)
    price: float = Field(ge=0)
    currency: str = "USD"
    location: ListingLocation
    seller_type: SellerType
    photos: list[ListingPhoto] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime
    source_records: list[NormalizedListing] = Field(min_length=1)

    @field_validator("vin")
    @classmethod
    def _vin(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        try:
            return validate_vin(value)
        except VinError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("make", "model")
    @classmethod
    def _required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("trim")
    @classmethod
    def _trim(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return code

    @field_validator("price")
    @classmethod
    def _finite_price(cls, value: float) -> float:
        if value != value or value == float("inf"):
            raise ValueError("price must be finite")
        return float(value)

    @field_validator("first_seen", "last_seen")
    @classmethod
    def _seen(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @model_validator(mode="after")
    def _seen_order(self) -> "CanonicalListing":
        if self.last_seen < self.first_seen:
            raise ValueError("last_seen is earlier than first_seen")
        return self


def build_provenance(
    *,
    source: str,
    source_url: str,
    fetched_at: datetime,
    payload: dict[str, Any],
) -> RawProvenance:
    """Hash the adapter's raw object. The hash is not part of the payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return RawProvenance(
        source=source,
        source_url=source_url,
        fetched_at=fetched_at,
        payload=payload,
        payload_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def url_photo(url: str) -> ListingPhoto:
    """Hash a photo URL. Dedupe ignores this; it is not image bytes."""
    digest = hashlib.sha256(url.strip().encode()).hexdigest()
    return ListingPhoto(url=url.strip(), sha256=digest, hash_kind=PhotoHashKind.URL)


def content_photo(url: str, content: bytes) -> ListingPhoto:
    return ListingPhoto(
        url=url.strip(),
        sha256=hashlib.sha256(content).hexdigest(),
        hash_kind=PhotoHashKind.CONTENT,
    )


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _require_http_url(value: str, label: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be an http(s) URL")
    return value.strip()


def _require_source_url(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("local://") and len(stripped) > len("local://"):
        return stripped
    return _require_http_url(stripped, "source_url")
