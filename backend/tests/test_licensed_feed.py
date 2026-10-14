"""Licensed feed adapters. Recorded JSON and XML only. No network."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

import backend.agents.ingestion.licensed_feed as licensed_feed
from backend.agents.ingestion import bat, classic_com, ebay, live_fetch_policies, tcv
from backend.agents.ingestion.dedupe import dedupe
from backend.agents.ingestion.ebay_browse import POLICY as EBAY_BROWSE_POLICY
from backend.agents.ingestion.licensed_feed import (
    JSON_FEED_ID,
    XML_FEED_ID,
    FeedLoader,
    FeedTarget,
    JsonFeedProvider,
    MissingLicensedFeedCredentials,
    XmlFeedProvider,
    json_feed_configured,
    registered_feed_sources,
    xml_feed_configured,
)
from backend.agents.ingestion.policy import USER_AGENT
from shared.schemas.deal import DealSource
from shared.schemas.listing import ListingLocation, MatchMethod, NormalizedListing, SellerType, build_provenance
from shared.schemas.market import PriceKind, Source, vehicle_key
from shared.vin import vin_key

ROOT = Path(__file__).resolve().parents[2]
LISTINGS = ROOT / "shared" / "fixtures" / "listings"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingestion"
VIN = "1HGCM82633A004352"
FETCHED_AT = datetime(2026, 8, 15, tzinfo=timezone.utc)

JSON_CONFIG = {
    "id": JSON_FEED_ID,
    "name": "Licensed JSON feed",
    "seller_type": "marketplace",
    "path": "/listings",
    "records_path": "records",
    "next_path": "next_page",
    "page_param": "page",
    "page_size_param": "page_size",
    "page_size": 50,
    "min_interval_seconds": 2.0,
    "fields": {
        "vin": "vin",
        "year": "year",
        "make": "make",
        "model": "model",
        "trim": "trim",
        "mileage": "odometer",
        "asking_price": "asking_price",
        "sold_price": "sold_price",
        "currency": "currency",
        "title": "title",
        "url": "listing_url",
        "city": "city",
        "region": "region",
        "postal_code": "postal_code",
        "country": "country",
        "photo": "photo_url",
    },
}

XML_CONFIG = {
    "id": XML_FEED_ID,
    "name": "Licensed XML feed",
    "seller_type": "dealer",
    "base_url": "https://feeds.example",
    "record_tag": "record",
    "page_size": 1,
    "min_interval_seconds": 2.0,
    "fields": {
        "vin": "vin",
        "year": "year",
        "make": "make",
        "model": "model",
        "trim": "trim",
        "mileage": "mileage",
        "asking_price": "asking_price",
        "sold_price": "sold_price",
        "currency": "currency",
        "title": "title",
        "url": "listing_url",
        "city": "city",
        "region": "region",
        "postal_code": "postal_code",
        "country": "country",
    },
}

_FEED_ENV = (
    "LICENSED_FEED_BASE_URL",
    "LICENSED_FEED_API_KEY",
    "LICENSED_FEED_XML_URL",
    "LICENSED_FEED_XML_PATH",
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("licensed feed tests must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    for name in _FEED_ENV:
        monkeypatch.delenv(name, raising=False)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


class RecordingLoader(FeedLoader):
    def __init__(self, pages: dict[str, bytes]) -> None:
        self.pages = pages
        self.targets: list[FeedTarget] = []

    def load(self, target: FeedTarget) -> bytes:
        self.targets.append(target)
        page = (target.params or {}).get("page", "1")
        return self.pages[page]


class BoomLoader(FeedLoader):
    def load(self, target: FeedTarget) -> bytes:
        raise AssertionError("loader must not run without credentials")


def _json_provider(clock: FakeClock | None = None) -> tuple[JsonFeedProvider, RecordingLoader]:
    loader = RecordingLoader(
        {
            "1": (FIXTURES / "licensed_feed_page_1.json").read_bytes(),
            "2": (FIXTURES / "licensed_feed_page_2.json").read_bytes(),
        }
    )
    if clock is None:
        clock = FakeClock()
    provider = JsonFeedProvider(
        JSON_CONFIG,
        base_url="https://feeds.example",
        api_key="deaven-test-feed-key",
        loader=loader,
        clock=clock.now,
        sleep=clock.sleep,
    )
    return provider, loader


def _load_listing(name: str) -> NormalizedListing:
    raw = json.loads((LISTINGS / name).read_text())
    payload = raw.pop("payload")
    fetched_at = datetime.fromisoformat(raw.pop("fetched_at"))
    raw["provenance"] = build_provenance(
        source=raw["source"],
        source_url=raw["source_url"],
        fetched_at=fetched_at,
        payload=payload,
    ).model_dump(mode="json")
    return NormalizedListing.model_validate(raw)


def test_json_page_maps_asking_price_and_keeps_sold_separate():
    provider, _loader = _json_provider()
    page = provider.fetch_page(fetched_at=FETCHED_AT)
    assert len(page.listings) == 1
    listing = page.listings[0]
    assert isinstance(page.source, Source)
    assert page.source is provider.source
    assert registered_feed_sources()[listing.source] is provider.source
    assert provider.source.code is DealSource.MANUAL
    assert provider.source.name == "Licensed JSON feed"
    assert provider.source.kind is SellerType.MARKETPLACE
    assert provider.source.robots_ok is False
    assert provider.source.tos_reviewed is False
    assert listing.source == JSON_FEED_ID
    assert listing.seller_type is provider.source.kind
    assert listing.provenance.source == JSON_FEED_ID
    assert listing.provenance.payload["source_name"] == "Licensed JSON feed"
    assert listing.provenance.payload["source_code"] == DealSource.MANUAL.value
    assert listing.provenance.payload["record"]["sold_price"] == "31000.00"
    assert listing.vin == vin_key("1hg-cm82633-a004352") == VIN
    assert listing.price == 32950
    assert listing.mileage == 62210
    assert listing.location.label == "Austin, TX 78701"
    assert listing.photos[0].url == "https://img.example/feed-m3.jpg"
    assert [(row.kind, row.amount) for row in page.prices] == [
        (PriceKind.ASKING, 32950),
        (PriceKind.SOLD, 31000),
    ]
    assert page.prices[0].listing_id == page.prices[1].listing_id == listing.observation_id
    assert listing.price != 31000


def test_json_pagination_uses_the_injected_loader_and_rate_limit():
    clock = FakeClock()
    provider, loader = _json_provider(clock)
    page = provider.fetch_all(fetched_at=FETCHED_AT)
    assert [item.source_url for item in page.listings] == [
        "https://feeds.example/listings/rec-bmw",
        "https://feeds.example/listings/rec-honda",
    ]
    assert loader.targets[0].url == "https://feeds.example/listings"
    assert loader.targets[0].params["page"] == "1"
    assert loader.targets[1].params["page"] == "2"
    assert loader.targets[0].headers["Authorization"] == "Bearer deaven-test-feed-key"
    assert loader.targets[0].headers["User-Agent"] == USER_AGENT
    assert clock.slept == [2.0]
    honda = page.listings[1]
    honda_prices = [row for row in page.prices if row.listing_id == honda.observation_id]
    assert [(row.kind, row.amount) for row in honda_prices] == [(PriceKind.ASKING, 42000)]


def test_xml_file_keeps_the_row_and_a_separate_sold_price():
    clock = FakeClock()
    provider = XmlFeedProvider(
        XML_CONFIG,
        base_url="https://feeds.example",
        path=str(FIXTURES / "licensed_feed.xml"),
        clock=clock.now,
        sleep=clock.sleep,
    )
    assert provider.enabled is True
    page = provider.fetch_all(fetched_at=FETCHED_AT)
    assert clock.slept == [2.0]
    assert [item.source_url for item in page.listings] == [
        "https://feeds.example/xml/bmw",
        "https://feeds.example/xml/rx7",
    ]
    bmw, rx7 = page.listings
    assert provider.source.name == "Licensed XML feed"
    assert provider.source.kind is SellerType.DEALER
    assert bmw.seller_type is SellerType.DEALER
    assert bmw.source == XML_FEED_ID
    assert registered_feed_sources()[XML_FEED_ID] is provider.source
    assert bmw.price == 30100
    assert bmw.vin == VIN
    assert "<vin>1HGCM82633A004352</vin>" in bmw.provenance.payload["record_xml"]
    assert "<sold_price>28000</sold_price>" in bmw.provenance.payload["record_xml"]
    assert bmw.provenance.payload["record"]["asking_price"] == "30100"
    assert [(row.kind, row.amount) for row in page.prices if row.listing_id == bmw.observation_id] == [
        (PriceKind.ASKING, 30100),
        (PriceKind.SOLD, 28000),
    ]
    assert rx7.vin is None
    assert rx7.price == 32500
    assert rx7.location == ListingLocation(
        label="Portland, OR 97202",
        city="Portland",
        region="OR",
        country="US",
    )
    assert [(row.kind, row.amount) for row in page.prices if row.listing_id == rx7.observation_id] == [
        (PriceKind.ASKING, 32500),
        (PriceKind.SOLD, 30000),
    ]


def test_feed_listings_dedupe_with_other_sources_by_vehicle_key():
    clock = FakeClock()
    json_provider, _loader = _json_provider(clock)
    xml_provider = XmlFeedProvider(
        XML_CONFIG,
        base_url="https://feeds.example",
        path=str(FIXTURES / "licensed_feed.xml"),
        clock=clock.now,
        sleep=clock.sleep,
    )
    json_page = json_provider.fetch_all(fetched_at=FETCHED_AT)
    xml_page = xml_provider.fetch_all(fetched_at=FETCHED_AT)
    ebay = _load_listing("ebay_e46.json")
    no_vin = _load_listing("no_vin.json")
    json_bmw, json_honda = json_page.listings
    xml_bmw, xml_rx7 = xml_page.listings
    assert vehicle_key(json_bmw) == vehicle_key(xml_bmw) == vehicle_key(ebay) == VIN
    assert vehicle_key(xml_rx7) == vehicle_key(no_vin)
    assert vehicle_key(json_honda) != VIN

    result = dedupe([json_bmw, json_honda, xml_bmw, xml_rx7, ebay, no_vin])
    assert [(cluster.match_method, cluster.vehicle_key) for cluster in result.clusters] == [
        (MatchMethod.VIN, VIN),
        (MatchMethod.VIN, json_honda.vin),
        (MatchMethod.FUZZY, vehicle_key(no_vin)),
    ]
    assert result.clusters[0].listing_ids == [
        json_bmw.observation_id,
        xml_bmw.observation_id,
        ebay.observation_id,
    ]
    assert result.clusters[2].listing_ids == [xml_rx7.observation_id, no_vin.observation_id]
    amounts = {
        json_bmw.observation_id: 32950,
        xml_bmw.observation_id: 30100,
        xml_rx7.observation_id: 32500,
    }
    for row in result.prices:
        if row.listing_id in amounts:
            assert row.kind is PriceKind.ASKING
            assert row.amount == amounts[row.listing_id]


def test_missing_credentials_stop_before_the_loader():
    assert json_feed_configured() is False
    assert xml_feed_configured() is False
    boom = BoomLoader()
    with pytest.raises(MissingLicensedFeedCredentials):
        JsonFeedProvider.from_env(JSON_CONFIG, loader=boom)
    with pytest.raises(MissingLicensedFeedCredentials):
        XmlFeedProvider.from_env(XML_CONFIG, loader=boom)

    disabled = JsonFeedProvider(JSON_CONFIG, base_url="", api_key="", loader=boom)
    assert disabled.enabled is False
    with pytest.raises(MissingLicensedFeedCredentials):
        disabled.fetch_page(fetched_at=FETCHED_AT)
    with pytest.raises(MissingLicensedFeedCredentials):
        disabled.fetch_all(fetched_at=FETCHED_AT)


def test_live_list_keeps_browse_only_until_feed_env_is_set(monkeypatch):
    assert live_fetch_policies() == [EBAY_BROWSE_POLICY]
    assert bat.LIVE_FETCH_ALLOWED is False
    assert classic_com.LIVE_FETCH_ALLOWED is False
    assert ebay.LIVE_FETCH_ALLOWED is False
    assert tcv.LIVE_FETCH_ALLOWED is False

    monkeypatch.setenv("LICENSED_FEED_XML_PATH", str(FIXTURES / "licensed_feed.xml"))
    assert live_fetch_policies() == [EBAY_BROWSE_POLICY]

    monkeypatch.setenv("LICENSED_FEED_BASE_URL", "https://feeds.example")
    monkeypatch.setenv("LICENSED_FEED_API_KEY", "deaven-test-feed-key")
    policies = live_fetch_policies()
    assert policies[0] is EBAY_BROWSE_POLICY
    assert len(policies) == 2
    assert policies[1].live_fetch_allowed is True
    assert policies[1].review_status == "licensed feed"
    assert "Licensed JSON feed" in policies[1].tos_note
    assert bat.POLICY not in policies

    monkeypatch.delenv("LICENSED_FEED_BASE_URL")
    monkeypatch.delenv("LICENSED_FEED_API_KEY")
    monkeypatch.delenv("LICENSED_FEED_XML_PATH")
    monkeypatch.setenv("LICENSED_FEED_XML_URL", "https://feeds.example/drop.xml")
    policies = live_fetch_policies()
    assert policies[0] is EBAY_BROWSE_POLICY
    assert len(policies) == 2
    assert "Licensed XML feed" in policies[1].tos_note
    assert policies[1].tos_url == "https://feeds.example/drop.xml"


def test_env_example_names_feed_settings_without_values():
    text = (ROOT / "backend" / ".env.example").read_text()
    named = [
        line
        for line in text.splitlines()
        if line.startswith("LICENSED_FEED_")
    ]
    assert named == [
        "LICENSED_FEED_BASE_URL=",
        "LICENSED_FEED_API_KEY=",
        "LICENSED_FEED_XML_URL=",
        "LICENSED_FEED_XML_PATH=",
    ]
    source = Path(licensed_feed.__file__).read_text()
    assert "deaven-test-feed-key" not in source
