"""Offline source adapters and vehicle_key dedupe. No network."""

from __future__ import annotations

import base64
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

import backend.agents.ingestion.dedupe as dedupe_mod
import backend.agents.ingestion.ebay_browse as ebay_browse
from backend.agents.ingestion import bat, classic_com, ebay, live_fetch_policies, tcv
from backend.agents.ingestion.dedupe import dedupe
from backend.agents.ingestion.ebay_browse import MissingEbayCredentials, fetch_search, parse_browse_payload
from backend.agents.ingestion.extract import KM_TO_MILES
from backend.agents.ingestion.policy import LiveFetchBlocked, RateLimiter, RobotsDenied, begin_live_fetch, robots_allowed
from shared.schemas.listing import ListingLocation, MatchMethod, NormalizedListing, SellerType, build_provenance
from shared.schemas.market import PriceKind, PriceObservation, vehicle_key, vehicle_key_for
from shared.vin import vin_key

ROOT = Path(__file__).resolve().parents[2]
LISTINGS = ROOT / "shared" / "fixtures" / "listings"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingestion"
HTML = FIXTURES / "html"
ROBOTS = FIXTURES / "robots"
VIN = "1HGCM82633A004352"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("ingestion tests must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


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


def _fetched_at(name: str) -> datetime:
    raw = json.loads((LISTINGS / name).read_text())
    return datetime.fromisoformat(raw["fetched_at"])


def _prices(name: str) -> list[PriceObservation]:
    return [PriceObservation.model_validate(row) for row in json.loads((LISTINGS / name).read_text())]


def _assert_same_observation(parsed: NormalizedListing, fixture: NormalizedListing) -> None:
    assert parsed.observation_id == fixture.observation_id
    assert parsed.vin == fixture.vin
    assert parsed.year == fixture.year
    assert parsed.make == fixture.make
    assert parsed.model == fixture.model
    assert parsed.trim == fixture.trim
    assert parsed.mileage == fixture.mileage
    assert parsed.price == fixture.price
    assert parsed.currency == fixture.currency
    assert parsed.location == fixture.location
    assert parsed.seller_type is fixture.seller_type
    assert parsed.source == fixture.source
    assert parsed.source_url == fixture.source_url
    assert parsed.title == fixture.title
    assert [photo.url for photo in parsed.photos] == [photo.url for photo in fixture.photos]
    assert parsed.first_seen == fixture.first_seen
    assert parsed.last_seen == fixture.last_seen
    assert parsed.provenance.fetched_at == fixture.provenance.fetched_at


def test_recorded_bat_and_ebay_html_match_market_fixtures():
    bat_page = bat.parse((HTML / "bat_e46.html").read_text(), fetched_at=_fetched_at("bat_e46.json"))
    ebay_page = ebay.parse((HTML / "ebay_e46.html").read_text(), fetched_at=_fetched_at("ebay_e46.json"))
    assert len(bat_page.listings) == 1
    assert len(ebay_page.listings) == 1
    _assert_same_observation(bat_page.listings[0], _load_listing("bat_e46.json"))
    _assert_same_observation(ebay_page.listings[0], _load_listing("ebay_e46.json"))
    assert bat_page.prices == _prices("bat_e46_prices.json")
    assert ebay_page.prices == _prices("ebay_e46_prices.json")
    assert vin_key("1hg-cm82633-a004352") == ebay_page.listings[0].vin == VIN


def test_dedupe_reuses_market_fixtures_and_calls_vehicle_key(monkeypatch):
    calls: list[str] = []
    real = dedupe_mod.vehicle_key

    def wrapped(listing: NormalizedListing) -> str:
        calls.append(listing.observation_id)
        return real(listing)

    monkeypatch.setattr(dedupe_mod, "vehicle_key", wrapped)
    source = Path(dedupe_mod.__file__).read_text()
    assert "def vin_key" not in source
    assert "def fuzzy_vehicle_key" not in source
    assert "sha256" not in source
    assert "mileage_band" not in source

    bat_listing = _load_listing("bat_e46.json")
    ebay_listing = _load_listing("ebay_e46.json")
    result = dedupe([bat_listing, ebay_listing])

    assert calls == [bat_listing.observation_id, ebay_listing.observation_id]
    assert len(result.clusters) == 1
    cluster = result.clusters[0]
    assert cluster.vehicle_key == VIN
    assert cluster.match_method is MatchMethod.VIN
    assert cluster.listing_ids == [bat_listing.observation_id, ebay_listing.observation_id]
    assert [(row.listing_id, row.amount, row.kind) for row in result.prices] == [
        (bat_listing.observation_id, bat_listing.price, PriceKind.ASKING),
        (ebay_listing.observation_id, ebay_listing.price, PriceKind.ASKING),
    ]
    assert {row.listing_id for row in _prices("bat_e46_prices.json")} == {bat_listing.observation_id}
    assert {row.listing_id for row in _prices("ebay_e46_prices.json")} == {ebay_listing.observation_id}


def test_classic_html_fuzzy_groups_with_no_vin_fixture():
    page = classic_com.parse(
        (HTML / "classic_rx7.html").read_text(),
        fetched_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    assert len(page.listings) == 2
    no_vin = _load_listing("no_vin.json")
    low, high = page.listings
    assert low.vin is None and high.vin is None
    assert low.seller_type is SellerType.MARKETPLACE
    assert vehicle_key(low) == vehicle_key(no_vin)
    assert vehicle_key(high) != vehicle_key(no_vin)

    result = dedupe([low, high, no_vin])
    assert [cluster.match_method for cluster in result.clusters] == [MatchMethod.FUZZY, MatchMethod.FUZZY]
    assert result.clusters[0].vehicle_key == vehicle_key(no_vin)
    assert result.clusters[0].listing_ids == [low.observation_id, no_vin.observation_id]
    assert result.clusters[1].listing_ids == [high.observation_id]
    assert [row.amount for row in result.prices] == [low.price, no_vin.price, high.price]


def test_invalid_vin_html_takes_the_fuzzy_path():
    page = bat.parse(
        (HTML / "bat_invalid_vin.html").read_text(),
        fetched_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    assert len(page.listings) == 1
    listing = page.listings[0]
    raw = json.loads((LISTINGS / "invalid_vin.json").read_text())
    location = ListingLocation.model_validate(raw["location"])
    assert listing.vin is None
    assert vin_key(raw["vin"]) is None
    assert listing.provenance.payload["vin"] == raw["vin"]
    assert listing.year == raw["year"]
    assert listing.make == raw["make"]
    assert listing.model == raw["model"]
    assert listing.trim == raw["trim"]
    assert listing.mileage == raw["mileage"]
    assert listing.location == location
    assert vehicle_key(listing) == vehicle_key_for(
        vin=raw["vin"],
        year=raw["year"],
        make=raw["make"],
        model=raw["model"],
        trim=raw["trim"],
        mileage=raw["mileage"],
        location=location,
    )
    result = dedupe([listing])
    assert result.clusters[0].match_method is MatchMethod.FUZZY
    assert result.clusters[0].vehicle_key == vehicle_key(listing)
    assert result.prices[0].kind is PriceKind.ASKING
    assert result.prices[0].amount == 18000


def test_tcv_keeps_yen_and_records_kilometers():
    page = tcv.parse(
        (HTML / "tcv_supra.html").read_text(),
        fetched_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )
    assert len(page.listings) == 1
    listing = page.listings[0]
    assert listing.source == "tcv"
    assert listing.seller_type is SellerType.AUCTION
    assert listing.currency == "JPY"
    assert listing.price == 1_850_000
    assert listing.vin == "1M8GDM9AXKP042788"
    assert listing.mileage == int(round(85_000 * KM_TO_MILES))
    assert listing.provenance.payload["mileage_km"] == 85_000
    assert listing.location.label == "Osaka, Japan"
    assert listing.location.country == "JP"
    assert listing.source_url == "https://www.tc-v.com/used_car/toyota/supra/88421"
    assert page.prices[0].currency == "JPY"
    result = dedupe([listing])
    assert result.clusters[0].match_method is MatchMethod.VIN
    assert result.clusters[0].vehicle_key == listing.vin
    assert result.prices[0].listing_id == listing.observation_id


@pytest.mark.parametrize(
    ("adapter", "robots_name", "allow_url", "deny_url", "site_name"),
    [
        (
            bat,
            "bat.txt",
            "https://bringatrailer.com/listing/deaven-demo-2003-bmw-m3",
            "https://bringatrailer.com/private/secret",
            "Bring a Trailer",
        ),
        (
            classic_com,
            "classic_com.txt",
            "https://www.classic.com/veh/deaven-demo-1993-mazda-rx7",
            "https://www.classic.com/account/settings",
            "classic.com",
        ),
        (
            ebay,
            "ebay.txt",
            "https://www.ebay.com/itm/deaven-demo-2003-bmw-m3",
            "https://www.ebay.com/signin/",
            "eBay",
        ),
        (
            tcv,
            "tcv.txt",
            "https://www.tc-v.com/used_car/toyota/supra/88421",
            "https://www.tc-v.com/mypage/",
            "tc-v.com",
        ),
    ],
)
def test_each_source_has_robots_check_tos_note_and_rate_limit(
    adapter, robots_name, allow_url, deny_url, site_name
):
    robots = (ROBOTS / robots_name).read_text()
    assert site_name in adapter.POLICY.tos_note
    assert "credential" in adapter.POLICY.tos_note.casefold()
    assert adapter.POLICY.robots_url == adapter.POLICY.source.base_url.rstrip("/") + "/robots.txt"
    assert adapter.POLICY.source.robots_ok is False
    assert adapter.POLICY.source.tos_reviewed is False
    assert robots_allowed(robots, "SomeOtherBot/1.0", allow_url) is False
    assert robots_allowed(robots, adapter.POLICY.user_agent, allow_url) is True
    assert robots_allowed(robots, adapter.POLICY.user_agent, deny_url) is False

    clock = FakeClock()
    limiter = adapter.limiter(clock=clock.now, sleep=clock.sleep)
    adapter.authorize(robots, allow_url, limiter)
    with pytest.raises(RobotsDenied):
        adapter.authorize(robots, deny_url, limiter)
    assert clock.slept == []
    adapter.authorize(robots, allow_url, limiter)
    assert clock.slept == [adapter.POLICY.min_interval_seconds]
    assert adapter.POLICY.source.robots_ok is False


def test_rate_limiters_do_not_share_a_clock():
    intervals = {
        bat.POLICY.min_interval_seconds,
        classic_com.POLICY.min_interval_seconds,
        ebay.POLICY.min_interval_seconds,
        tcv.POLICY.min_interval_seconds,
    }
    assert intervals == {8.0, 6.0, 3.0, 5.0}
    bat_clock = FakeClock()
    ebay_clock = FakeClock()
    bat_limiter = bat.limiter(clock=bat_clock.now, sleep=bat_clock.sleep)
    ebay_limiter = ebay.limiter(clock=ebay_clock.now, sleep=ebay_clock.sleep)
    bat_limiter.acquire()
    ebay_limiter.acquire()
    bat_limiter.acquire()
    assert bat_clock.slept == [bat.POLICY.min_interval_seconds]
    assert ebay_clock.slept == []


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        ebay.parse("<html></html>", fetched_at=datetime(2026, 7, 20))


def test_terms_keep_html_sources_parser_only():
    expected = {
        bat: (
            "https://bringatrailer.com/terms-of-use/",
            "software robots, spider, crawlers",
        ),
        classic_com: (
            "https://www.classic.com/about/terms-conditions/",
            "express prior written consent",
        ),
        ebay: (
            "https://www.ebay.com.au/help/policies/member-behaviour-policies/user-agreement?id=4259",
            "robot, spider, scraper",
        ),
        tcv: (
            "https://www.tc-v.com/about/termsofuse/",
            "Article 11.1.11",
        ),
    }
    for adapter, (url, clause) in expected.items():
        assert adapter.LIVE_FETCH_ALLOWED is False
        assert adapter.POLICY.live_fetch_allowed is False
        assert adapter.POLICY.review_status == "pending RJ decision"
        assert adapter.POLICY.tos_url == url
        assert url in adapter.POLICY.tos_note
        assert clause in adapter.POLICY.tos_note
        assert "pending RJ decision" in adapter.POLICY.tos_note
        clock = FakeClock()
        limiter = adapter.limiter(clock=clock.now, sleep=clock.sleep)
        with pytest.raises(LiveFetchBlocked):
            begin_live_fetch(adapter.POLICY, "User-agent: *\nDisallow:\n", "https://example.invalid/item", limiter)
        assert clock.slept == []


def test_live_fetch_list_is_the_browse_api(monkeypatch):
    for name in (
        "LICENSED_FEED_BASE_URL",
        "LICENSED_FEED_API_KEY",
        "LICENSED_FEED_XML_URL",
        "LICENSED_FEED_XML_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    policies = live_fetch_policies()
    assert policies == [ebay_browse.POLICY]
    assert ebay_browse.LIVE_FETCH_ALLOWED is True
    assert ebay_browse.POLICY.review_status == "official Browse API"
    assert ebay.POLICY not in policies
    clock = FakeClock()
    limiter = RateLimiter(ebay_browse.POLICY.min_interval_seconds, clock=clock.now, sleep=clock.sleep)
    robots = "User-agent: *\nDisallow:\n"
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    begin_live_fetch(ebay_browse.POLICY, robots, url, limiter)
    begin_live_fetch(ebay_browse.POLICY, robots, url, limiter)
    assert clock.slept == [ebay_browse.POLICY.min_interval_seconds]


def test_browse_recorded_json_maps_the_ebay_fixture():
    item = json.loads((FIXTURES / "ebay_browse_item.json").read_text())
    fetched_at = _fetched_at("ebay_e46.json")
    fixture = _load_listing("ebay_e46.json")
    page = parse_browse_payload(item, fetched_at=fetched_at)
    wrapped = parse_browse_payload({"itemSummaries": [item], "total": 1}, fetched_at=fetched_at)
    assert len(page.listings) == 1
    listing = page.listings[0]
    assert wrapped.listings[0].observation_id == listing.observation_id
    assert listing.observation_id == fixture.observation_id
    assert listing.vin == fixture.vin == VIN
    assert listing.price == 32950
    assert listing.mileage == 62210
    assert listing.location.label == "Austin, TX 78701"
    assert listing.currency == "USD"
    assert listing.source_url == fixture.source_url
    assert vehicle_key(listing) == VIN
    assert page.prices[0].kind is PriceKind.ASKING
    assert page.prices[0].amount == 32950
    assert page.prices[0].listing_id == listing.observation_id
    empty = parse_browse_payload({"itemSummaries": [{"title": "2003 BMW M3"}]}, fetched_at=fetched_at)
    assert empty.listings == []


def test_browse_fetch_uses_a_mocked_transport(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    fetched_at = datetime(2026, 7, 20, tzinfo=timezone.utc)

    def refused(*args, **kwargs):
        raise AssertionError("transport must not run without credentials")

    with pytest.raises(MissingEbayCredentials):
        fetch_search("2003 BMW M3", fetched_at=fetched_at, transport=refused)

    monkeypatch.setenv("EBAY_CLIENT_ID", "deaven-test-client")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "deaven-test-secret")
    item = json.loads((FIXTURES / "ebay_browse_item.json").read_text())
    calls: list[dict] = []

    def transport(method, url, *, headers, body=None, params=None):
        calls.append({"method": method, "url": url, "headers": headers, "body": body, "params": params})
        if url == ebay_browse.TOKEN_URL:
            return {"access_token": "recorded-token", "expires_in": 7200, "token_type": "Application Access Token"}
        return {"itemSummaries": [item]}

    page = fetch_search("2003 BMW M3", fetched_at=fetched_at, transport=transport)
    assert len(calls) == 2
    token_call, search_call = calls
    decoded = base64.b64decode(token_call["headers"]["Authorization"].split()[1]).decode()
    assert decoded == "deaven-test-client:deaven-test-secret"
    assert token_call["method"] == "POST"
    assert token_call["url"] == ebay_browse.TOKEN_URL
    assert "client_credentials" in token_call["body"]
    assert search_call["headers"]["Authorization"] == "Bearer recorded-token"
    assert search_call["headers"]["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_MOTORS"
    assert search_call["url"] == ebay_browse.SEARCH_URL
    assert search_call["params"]["category_ids"] == "6001"
    assert page.listings[0].vin == VIN
    source = Path(ebay_browse.__file__).read_text()
    assert "deaven-test-client" not in source
    assert "deaven-test-secret" not in source


def test_env_example_names_ebay_credentials_without_values():
    text = (ROOT / "backend" / ".env.example").read_text()
    named = [
        line
        for line in text.splitlines()
        if line.startswith("EBAY_CLIENT_ID=") or line.startswith("EBAY_CLIENT_SECRET=")
    ]
    assert named == ["EBAY_CLIENT_ID=", "EBAY_CLIENT_SECRET="]
