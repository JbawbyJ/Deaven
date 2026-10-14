"""ListingData contract. Fixtures only — no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.schemas.deal import DealPayload, DealSource, ListingData, normalize_trim

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ingestion" / "valid_listing_data.json"


def test_existing_constructor_still_works():
    listing = ListingData(title="2003 BMW M3 Coupe", price=28900)
    assert listing.price == 28900
    assert listing.asking_price == 28900
    assert listing.currency == "USD"
    assert listing.sold_price is None
    assert listing.sold_at is None
    assert listing.vin is None
    assert listing.region is None
    assert listing.zip is None
    assert listing.location is None
    assert listing.listing_id is None
    assert listing.canonical_id is None
    assert listing.trim_normalized is None
    assert listing.seller_type is None


def test_fixture_populates_the_agreed_fields():
    listing = ListingData.model_validate(json.loads(FIXTURE.read_text()))
    assert listing.price == 28900
    assert listing.asking_price == 28900
    assert listing.sold_price == 27000
    assert listing.sold_at is not None
    assert listing.currency == "USD"
    assert listing.location == "Austin, TX"
    assert listing.region == "TX"
    assert listing.zip == "78701"
    assert listing.lat == pytest.approx(30.2672)
    assert listing.lng == pytest.approx(-97.7431)
    assert listing.vin == "1HGCM82633A004352"
    assert listing.trim == "SZ-R"
    assert listing.trim_normalized == "sz r"
    assert listing.source == "ebay"
    assert listing.source_id == "1234567890"
    assert listing.listing_id == "ebay:1234567890"
    assert listing.canonical_id is None
    assert listing.seller_type == "private"


def test_asking_price_is_an_alias_for_price():
    listing = ListingData(title="car", asking_price=1200)
    assert listing.price == 1200
    assert listing.asking_price == 1200
    with pytest.raises(ValidationError, match="asking_price"):
        ListingData(title="car", price=1200, asking_price=1300)


def test_listing_id_round_trip_and_conflicts():
    from_id = ListingData(title="car", price=1, listing_id="bat:9988")
    assert from_id.source == "bat"
    assert from_id.source_id == "9988"
    assert from_id.listing_id == "bat:9988"

    from_enum = ListingData(
        title="car",
        price=1,
        source=DealSource.EBAY,
        source_id="42",
    )
    assert from_enum.listing_id == "ebay:42"

    with pytest.raises(ValidationError, match="listing_id"):
        ListingData(title="car", price=1, source="ebay", source_id="1", listing_id="ebay:2")
    with pytest.raises(ValidationError, match="':'"):
        ListingData(title="car", price=1, source="ebay:motors", source_id="1")


def test_vin_is_normalized_and_check_digit_validated():
    listing = ListingData(title="car", price=1, vin="1hg-cm82633-a004352")
    assert listing.vin == "1HGCM82633A004352"
    blank = ListingData(title="car", price=1, vin="  ")
    assert blank.vin is None
    with pytest.raises(ValidationError, match="check digit"):
        ListingData(title="car", price=1, vin="JH4KA8260MC000000")


def test_trim_normalized_collapses_punctuation_without_a_vocabulary():
    assert normalize_trim("SZ-R") == "sz r"
    assert normalize_trim("  6-Speed   Manual ") == "6 speed manual"
    assert normalize_trim(None) is None
    assert normalize_trim("***") is None
    listing = ListingData(title="car", price=1, trim="AP2", trim_normalized="ignore me")
    assert listing.trim == "AP2"
    assert listing.trim_normalized == "ap2"


def test_coordinates_use_source_values_or_zip_centroids():
    pinned = ListingData(title="car", price=1, zip="78701", lat=40.0, lng=-105.0)
    assert pinned.lat == 40.0
    assert pinned.lng == -105.0

    unknown = ListingData(title="car", price=1, zip="00000")
    assert unknown.lat is None
    assert unknown.lng is None

    plus4 = ListingData(title="car", price=1, zip="78701-1234")
    assert plus4.lat == pytest.approx(30.2672)
    assert plus4.lng == pytest.approx(-97.7431)

    bare = ListingData(title="car", price=1)
    assert bare.lat is None and bare.lng is None

    with pytest.raises(ValidationError):
        ListingData(title="car", price=1, lat=91, lng=0)
    with pytest.raises(ValidationError):
        ListingData(title="car", price=1, lat=0, lng=181)
    with pytest.raises(ValidationError, match="together"):
        ListingData(title="car", price=1, lat=30.0)


def test_catalog_and_deal_payload_stay_compatible():
    from backend.agents.local_pipeline import listing_from_catalog
    from backend.data.catalog import CATALOG

    listing = listing_from_catalog(CATALOG[0])
    assert listing.price == listing.asking_price
    assert listing.currency == "USD"
    assert listing.location == "Austin, TX"
    assert listing.trim_normalized == "coupe"
    assert listing.listing_id is None
    assert listing.lat == pytest.approx(30.2672)
    assert listing.lng == pytest.approx(-97.7431)

    payload = DealPayload(source=DealSource.EBAY, url="https://example.com/itm/1", listing=listing)
    restored = DealPayload.model_validate(payload.model_dump(mode="json"))
    assert restored.listing.asking_price == listing.price
    assert restored.listing.title == listing.title
