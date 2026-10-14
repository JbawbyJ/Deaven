"""Market extensions on PR #3's listing types. Fixtures only — no network."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.schemas.deal import DealPayload, DealSource, ListingData
from shared.schemas.listing import (
    ListingLocation,
    MatchMethod,
    NormalizedListing,
    SellerType,
    build_provenance,
)
from shared.vin import vin_key

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "shared" / "fixtures" / "listings"
SCHEMA_DIR = ROOT / "shared" / "schemas" / "json"

BAT_URL = "https://bringatrailer.com/listing/deaven-demo-2003-bmw-m3"
EBAY_URL = "https://www.ebay.com/itm/deaven-demo-2003-bmw-m3"
RX7_URL = "https://www.hemmings.com/listing/deaven-demo-1993-mazda-rx7"
VIN = "1HGCM82633A004352"
INVALID_VIN = "JH4KA8260MC000000"


def _load_listing(name: str) -> NormalizedListing:
    raw = json.loads((FIXTURES / name).read_text())
    payload = raw.pop("payload")
    fetched_at = datetime.fromisoformat(raw.pop("fetched_at"))
    raw["provenance"] = build_provenance(
        source=raw["source"],
        source_url=raw["source_url"],
        fetched_at=fetched_at,
        payload=payload,
    ).model_dump(mode="json")
    return NormalizedListing.model_validate(raw)


def _deal(**overrides) -> DealPayload:
    unchecked = overrides.pop("unchecked", False)
    listing = {
        "title": "2003 BMW M3 Coupe",
        "price": 32950.0,
        "mileage": 62140,
        "year": 2003,
        "make": "BMW",
        "model": "M3",
        "trim": "Coupe",
        "vin": VIN,
        "location": "Austin, TX 78701",
        "seller_type": "private",
    }
    listing.update(overrides.pop("listing", {}))
    fields = {
        "deal_id": "deal-demo-m3",
        "source": DealSource.EBAY,
        "url": EBAY_URL,
        "ingested_at": datetime(2026, 7, 20, tzinfo=timezone.utc),
        "images": ["https://img.example/m3.jpg"],
        "listing": ListingData.model_construct(**listing) if unchecked else ListingData(**listing),
    }
    fields.update(overrides)
    return DealPayload(**fields)


def test_vin_key_returns_normalized_vin_or_none():
    assert vin_key(" 1hg-cm82633-a004352 ") == VIN
    assert vin_key(INVALID_VIN) is None
    assert vin_key("1HGCM82633A00435I") is None
    assert vin_key("1HGCM82633A00435O") is None
    assert vin_key("1HGCM82633A00435Q") is None
    assert vin_key("short") is None
    assert vin_key("") is None
    assert vin_key(None) is None  # type: ignore[arg-type]


def test_listing_fixtures_validate_and_same_car_shares_vin_key():
    from shared.schemas.market import vehicle_key

    bat = _load_listing("bat_e46.json")
    ebay = _load_listing("ebay_e46.json")

    assert bat.vin == ebay.vin == VIN
    assert bat.source == "bat"
    assert ebay.source == "ebay"
    assert bat.seller_type is SellerType.AUCTION
    assert ebay.seller_type is SellerType.MARKETPLACE
    assert vehicle_key(bat) == vehicle_key(ebay) == VIN
    assert bat.location.latitude == pytest.approx(30.2672)
    assert bat.location.longitude == pytest.approx(-97.7431)


def test_price_drop_on_the_shared_car():
    from shared.schemas.market import PriceKind, PriceObservation

    bat = _load_listing("bat_e46.json")
    ebay = _load_listing("ebay_e46.json")
    price_files = sorted(FIXTURES.glob("*prices.json"))
    assert [path.name for path in price_files] == ["bat_e46_prices.json", "ebay_e46_prices.json"]
    loaded = {
        path.name: [PriceObservation.model_validate(row) for row in json.loads(path.read_text())]
        for path in price_files
    }
    prices = loaded["bat_e46_prices.json"]
    assert prices
    assert {row.listing_id for row in prices} == {bat.observation_id}
    assert {row.listing_id for row in loaded["ebay_e46_prices.json"]} == {ebay.observation_id}
    asking = sorted(
        (row for row in prices if row.kind is PriceKind.ASKING),
        key=lambda row: row.observed_at,
    )
    assert len(asking) >= 2
    assert asking[-1].amount < asking[0].amount
    assert asking[-1].amount == bat.price


def test_missing_vin_uses_a_stable_fuzzy_hash():
    from shared.schemas.market import MatchMethod, VehicleCluster, vehicle_key

    listing = _load_listing("no_vin.json")
    assert listing.vin is None
    assert vin_key("") is None
    expected = hashlib.sha256(b"1993|mazda|rx-7|touring|70000-79999|97202").hexdigest()
    assert vehicle_key(listing) == expected
    cluster = VehicleCluster(
        vehicle_key=vehicle_key(listing),
        listing_ids=[listing.observation_id],
        match_method=MatchMethod.FUZZY,
    )
    assert cluster.match_method is MatchMethod.FUZZY


def test_invalid_vin_fixture_takes_the_fuzzy_path():
    from shared.schemas.market import fuzzy_vehicle_key, vehicle_key_for

    raw = json.loads((FIXTURES / "invalid_vin.json").read_text())
    location = ListingLocation.model_validate(raw["location"])
    assert vin_key(raw["vin"]) is None
    with pytest.raises(ValidationError, match="check digit"):
        NormalizedListing.model_validate(
            {
                "vin": raw["vin"],
                "year": raw["year"],
                "make": raw["make"],
                "model": raw["model"],
                "trim": raw["trim"],
                "mileage": raw["mileage"],
                "price": 18000,
                "seller_type": "marketplace",
                "source": "craigslist",
                "source_url": "https://example.com/listings/invalid-vin",
                "first_seen": "2026-05-01T00:00:00Z",
                "last_seen": "2026-05-02T00:00:00Z",
                "location": raw["location"],
                "provenance": build_provenance(
                    source="craigslist",
                    source_url="https://example.com/listings/invalid-vin",
                    fetched_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                    payload={"vin": raw["vin"]},
                ).model_dump(mode="json"),
            }
        )
    expected = hashlib.sha256(b"1991|acura|legend|l|140000-149999|80202").hexdigest()
    assert fuzzy_vehicle_key(
        year=raw["year"],
        make=raw["make"],
        model=raw["model"],
        trim=raw["trim"],
        mileage=raw["mileage"],
        location=location,
    ) == expected
    assert vehicle_key_for(
        vin=raw["vin"],
        year=raw["year"],
        make=raw["make"],
        model=raw["model"],
        trim=raw["trim"],
        mileage=raw["mileage"],
        location=location,
    ) == expected


def test_fuzzy_key_mileage_band_and_zip():
    from shared.schemas.market import fuzzy_vehicle_key

    place = ListingLocation(label="Portland, OR 97202", city="Portland", region="OR", country="US")
    low = fuzzy_vehicle_key(
        year=1993, make="MAZDA", model="RX-7", trim="Touring", mileage=70000, location=place
    )
    high = fuzzy_vehicle_key(
        year=1993, make="Mazda", model="rx-7", trim=" touring ", mileage=79999, location=place
    )
    next_band = fuzzy_vehicle_key(
        year=1993, make="Mazda", model="RX-7", trim="Touring", mileage=80000, location=place
    )
    other_zip = fuzzy_vehicle_key(
        year=1993,
        make="Mazda",
        model="RX-7",
        trim="Touring",
        mileage=78400,
        location=ListingLocation(label="Portland, OR 97214", city="Portland", region="OR"),
    )
    assert low == high
    assert low != next_band
    assert low != other_zip
    assert fuzzy_vehicle_key(
        year=1993, make="Mazda", model="RX-7", trim=None, mileage=None,
        location=ListingLocation(city="Portland", region="OR"),
    ) == hashlib.sha256(b"1993|mazda|rx-7||unknown|").hexdigest()


def test_none_from_vin_key_uses_fuzzy_even_if_a_vin_is_present(monkeypatch):
    import shared.schemas.market as market

    monkeypatch.setattr(market, "vin_key", lambda raw: None)
    listing = _load_listing("bat_e46.json")
    assert listing.vin == VIN
    assert market.vehicle_key(listing) != VIN
    assert len(market.vehicle_key(listing)) == 64


def test_source_reuses_deal_source_and_seller_type():
    from shared.schemas.market import Seller, source_for

    bat = source_for(DealSource.BRING_A_TRAILER)
    ebay = source_for("ebay")
    dealer = source_for(DealSource.AUTOTRADER)
    assert bat.kind is SellerType.AUCTION
    assert bat.code is DealSource.BRING_A_TRAILER
    assert bat.name == "Bring a Trailer"
    assert bat.robots_ok is False
    assert bat.tos_reviewed is False
    assert ebay.kind is SellerType.MARKETPLACE
    assert dealer.kind is SellerType.DEALER
    seller = Seller(name="Demo Motors", seller_type=SellerType.DEALER)
    assert seller.seller_type is SellerType.DEALER
    for code in DealSource:
        source = source_for(code)
        assert source.code is code
        assert isinstance(source.kind, SellerType)


def test_vehicle_cluster_rejects_singleton():
    from shared.schemas.market import VehicleCluster

    with pytest.raises(ValidationError, match="vin or fuzzy"):
        VehicleCluster(
            vehicle_key=VIN,
            listing_ids=["bd8f0e137da82645", "873b796649b684da"],
            match_method=MatchMethod.SINGLETON,
        )


def test_adapters_round_trip():
    from shared.schemas.adapters import deal_from_listing, listing_from_deal
    from shared.schemas.market import vehicle_key

    deal = _deal()
    listing = listing_from_deal(deal)
    assert isinstance(listing, NormalizedListing)
    assert listing.vin == VIN
    assert listing.source == "ebay"
    assert listing.seller_type is SellerType.MARKETPLACE
    assert listing.location.city == "Austin"
    assert listing.location.region == "TX"
    assert listing.location.label == "Austin, TX 78701"
    assert [photo.url for photo in listing.photos] == deal.images
    assert vehicle_key(listing) == VIN

    restored = deal_from_listing(listing)
    assert restored.url == deal.url
    assert restored.source == deal.source
    assert restored.listing.price == deal.listing.price
    assert restored.listing.vin == VIN
    assert restored.listing.year == 2003
    assert restored.listing.make == "BMW"
    assert restored.listing.model == "M3"
    assert restored.listing.trim == "Coupe"
    assert restored.listing.mileage == 62140
    assert restored.listing.title == deal.listing.title
    assert restored.listing.location == "Austin, TX 78701"
    assert restored.images == deal.images

    again = listing_from_deal(restored)
    assert vehicle_key(again) == vehicle_key(listing)
    assert again.price == listing.price
    assert again.source_url == listing.source_url

    invalid = listing_from_deal(_deal(listing={"vin": INVALID_VIN, "location": "Denver, CO 80202"}, unchecked=True))
    assert invalid.vin is None
    assert vin_key(INVALID_VIN) is None
    assert vehicle_key(invalid) == hashlib.sha256(
        b"2003|bmw|m3|coupe|60000-69999|80202"
    ).hexdigest()


def test_json_schemas_match_the_models():
    from scripts.export_schemas import rendered_schemas

    expected = rendered_schemas()
    on_disk = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(SCHEMA_DIR.glob("*.schema.json"))
    }
    assert on_disk == expected
    assert "NormalizedListing.schema.json" in expected
    assert "ListingLocation.schema.json" in expected
    assert "PriceObservation.schema.json" in expected
    assert "VehicleCluster.schema.json" in expected
    assert "bat" in expected["Source.schema.json"]
    assert "reserve_not_met" in expected["PriceObservation.schema.json"]
