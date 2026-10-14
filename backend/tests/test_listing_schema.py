"""Normalized listing schema. Fixtures only — no network."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.schemas.listing import (
    CanonicalListing,
    NormalizedListing,
    SellerType,
    build_provenance,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ingestion" / "valid_listing.json"
SEEN = datetime(2026, 8, 1, tzinfo=timezone.utc)
URL = "https://example.com/listings/m3"


def _provenance(payload: dict | None = None, **overrides):
    fields = {
        "source": "bat",
        "source_url": URL,
        "fetched_at": SEEN,
        "payload": payload if payload is not None else {"slug": "bmw-m3-2003"},
    }
    fields.update(overrides)
    return build_provenance(**fields)


def _listing(**overrides) -> dict:
    data = {
        "vin": "1HGCM82633A004352",
        "year": 2003,
        "make": "BMW",
        "model": "M3",
        "trim": "Coupe",
        "mileage": 62140,
        "price": 28900.0,
        "currency": "USD",
        "location": {
            "label": "Austin, TX",
            "city": "Austin",
            "region": "TX",
            "country": "US",
            "latitude": 30.2672,
            "longitude": -97.7431,
        },
        "seller_type": "auction",
        "source": "bat",
        "source_url": URL,
        "title": "2003 BMW M3 Coupe",
        "photos": [{"url": "https://img.example/a.jpg"}],
        "first_seen": SEEN,
        "last_seen": SEEN + timedelta(days=1),
        "provenance": _provenance().model_dump(),
    }
    data.update(overrides)
    return data


def test_fixture_listing_validates_and_normalizes():
    raw = json.loads(FIXTURE.read_text())
    payload = raw.pop("payload")
    raw["provenance"] = _provenance(payload=payload, fetched_at=datetime(2026, 8, 2, tzinfo=timezone.utc)).model_dump()
    listing = NormalizedListing.model_validate(raw)

    assert listing.vin == "1HGCM82633A004352"
    assert listing.currency == "USD"
    assert listing.seller_type is SellerType.AUCTION
    assert listing.location.latitude == pytest.approx(30.2672)
    assert listing.location.longitude == pytest.approx(-97.7431)
    assert listing.first_seen.tzinfo is not None
    assert listing.provenance.payload == payload
    assert listing.provenance.payload_sha256 == _provenance(payload=payload, fetched_at=listing.provenance.fetched_at).payload_sha256
    assert len(listing.observation_id) == 16
    assert listing.model_dump(mode="json")["seller_type"] == "auction"


def test_optional_fields_may_be_omitted():
    listing = NormalizedListing.model_validate(
        {
            "year": 1998,
            "make": "Toyota",
            "model": "Supra",
            "price": 0,
            "seller_type": "marketplace",
            "source": "ebay",
            "source_url": "local://supra-1998",
            "first_seen": SEEN,
            "last_seen": SEEN,
            "provenance": _provenance(source="ebay", source_url="local://supra-1998").model_dump(),
        }
    )
    assert listing.vin is None
    assert listing.trim is None
    assert listing.mileage is None
    assert listing.location.latitude is None
    assert listing.photos == []
    assert listing.currency == "USD"
    assert listing.seller_type is SellerType.MARKETPLACE


def test_vin_check_digit_is_enforced_on_the_listing():
    with pytest.raises(ValidationError, match="check digit"):
        NormalizedListing.model_validate(_listing(vin="JH4KA8260MC000000"))
    listing = NormalizedListing.model_validate(_listing(vin="1hg-cm82633-a004352"))
    assert listing.vin == "1HGCM82633A004352"


def test_location_coordinates_must_be_a_pair_inside_range():
    with pytest.raises(ValidationError, match="together"):
        NormalizedListing.model_validate(
            _listing(location={"city": "Austin", "latitude": 30.2})
        )
    with pytest.raises(ValidationError):
        NormalizedListing.model_validate(
            _listing(location={"latitude": 91.0, "longitude": 0.0})
        )
    with pytest.raises(ValidationError, match="ISO"):
        NormalizedListing.model_validate(_listing(location={"country": "USA"}))


def test_price_mileage_time_url_and_seller_type():
    with pytest.raises(ValidationError):
        NormalizedListing.model_validate(_listing(price=-1))
    with pytest.raises(ValidationError, match="finite"):
        NormalizedListing.model_validate(_listing(price=float("inf")))
    with pytest.raises(ValidationError):
        NormalizedListing.model_validate(_listing(mileage=-5))
    with pytest.raises(ValidationError):
        NormalizedListing.model_validate(_listing(mileage=2_000_001))
    with pytest.raises(ValidationError, match="earlier"):
        NormalizedListing.model_validate(
            _listing(last_seen=SEEN - timedelta(hours=1))
        )
    with pytest.raises(ValidationError, match="timezone"):
        NormalizedListing.model_validate(_listing(first_seen=datetime(2026, 8, 1)))
    with pytest.raises(ValidationError, match="source_url"):
        NormalizedListing.model_validate(_listing(source_url="ftp://files.example/car"))
    with pytest.raises(ValidationError):
        NormalizedListing.model_validate(_listing(seller_type="private"))
    with pytest.raises(ValidationError):
        NormalizedListing.model_validate(_listing(make="  "))
    with pytest.raises(ValidationError):
        NormalizedListing.model_validate(_listing(unexpected=True))


def test_photo_hash_and_provenance_hash():
    with pytest.raises(ValidationError, match="together"):
        NormalizedListing.model_validate(
            _listing(photos=[{"url": "https://img.example/a.jpg", "sha256": "ab" * 32}])
        )
    bad = _provenance().model_dump()
    bad["payload_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="does not match"):
        NormalizedListing.model_validate(_listing(provenance=bad))


def test_canonical_listing_keeps_source_records():
    record = NormalizedListing.model_validate(_listing())
    canonical = CanonicalListing(
        canonical_id=f"vin:{record.vin}",
        match_method="vin",
        vin=record.vin,
        year=record.year,
        make=record.make,
        model=record.model,
        trim=record.trim,
        mileage=record.mileage,
        price=record.price,
        location=record.location,
        seller_type=record.seller_type,
        photos=record.photos,
        first_seen=record.first_seen,
        last_seen=record.last_seen,
        source_records=[record],
    )
    assert canonical.source_records[0].source_url == URL
    assert canonical.match_method == "vin"
    with pytest.raises(ValidationError):
        CanonicalListing.model_validate(
            {**canonical.model_dump(), "source_records": [], "vin": "JH4KA8260MC000000"}
        )
