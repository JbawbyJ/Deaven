"""Dedupe, range, and price history against PR #8's listing fixtures.

Fixtures are copies of shared/fixtures/listings on agent/beebc-grok/listing-model
@5bc43fe. This branch does not import that module. No network.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

from backend.pricing.adapter import fuzzy_vehicle_key, vehicle_key, vehicle_key_for, vin_key
from backend.pricing.comps import ClusterResult, Estimate, assess_price, cluster_result, collapse_clusters, price_clusters
from backend.pricing.value import ListingFacts, rate_deal

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "listings"

VIN_A = "1HGCM82633A004352"
VIN_B = "1M8GDM9AXKP042788"
VIN_C = "JH4KA8268MC000000"
VIN_D = "JH4KA826XMC000001"
VIN_E = "JH4KA8261MC000002"
VIN_F = "JH4KA8263MC000003"
VIN_G = "JH4KA8265MC000004"
INVALID_VIN = "JH4KA8260MC000000"

AUSTIN = (30.2672, -97.7431)
DALLAS = (32.7767, -96.7970)
SEATTLE = (47.6062, -122.3321)

NO_VIN_KEY = hashlib.sha256(b"1993|mazda|rx-7|touring|70000-79999|97202").hexdigest()
INVALID_VIN_KEY = hashlib.sha256(b"1991|acura|legend|l|140000-149999|80202").hexdigest()


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


def _listing(name: str) -> dict:
    raw = _load(name)
    raw.pop("payload", None)
    raw.pop("fetched_at", None)
    return raw


def _prices(*names: str) -> list[dict]:
    rows: list[dict] = []
    for name in names:
        rows.extend(_load(name))
    return rows


def _facts(**overrides) -> ListingFacts:
    fields = dict(
        listing_id="comp",
        price=40_000.0,
        make="BMW",
        model="M3",
        trim="Coupe",
        year=2003,
        mileage=60_000,
        region="TX",
    )
    fields.update(overrides)
    return ListingFacts(**fields)


def _located(listing_id: str, vin: str, price: float, lat: float, lon: float) -> dict:
    return {
        "observation_id": listing_id,
        "vin": vin,
        "year": 2003,
        "make": "BMW",
        "model": "M3",
        "trim": "Coupe",
        "mileage": 60_000,
        "price": price,
        "currency": "USD",
        "location": {
            "label": "Coord only",
            "city": None,
            "region": None,
            "country": "US",
            "latitude": lat,
            "longitude": lon,
        },
        "seller_type": "marketplace",
        "source": "ebay",
        "source_url": f"https://example.com/{listing_id}",
        "first_seen": "2026-07-01T00:00:00Z",
        "last_seen": "2026-07-02T00:00:00Z",
    }


def test_vin_key_and_vehicle_key_match_listing_model_semantics():
    assert vin_key(" 1hg-cm82633-a004352 ") == VIN_A
    assert vin_key(INVALID_VIN) is None
    assert vin_key("short") is None
    assert vin_key("") is None

    bat = _listing("bat_e46.json")
    ebay = _listing("ebay_e46.json")
    assert vehicle_key(bat) == vehicle_key(ebay) == VIN_A

    no_vin = _listing("no_vin.json")
    assert no_vin.get("vin") is None
    assert vehicle_key(no_vin) == NO_VIN_KEY

    invalid = _load("invalid_vin.json")
    assert vehicle_key_for(
        vin=invalid["vin"],
        year=invalid["year"],
        make=invalid["make"],
        model=invalid["model"],
        trim=invalid["trim"],
        mileage=invalid["mileage"],
        location=invalid["location"],
    ) == INVALID_VIN_KEY
    assert fuzzy_vehicle_key(
        year=1993,
        make="MAZDA",
        model="RX-7",
        trim=" touring ",
        mileage=79_999,
        location={"label": "Portland, OR 97202"},
    ) == NO_VIN_KEY
    assert fuzzy_vehicle_key(
        year=1993,
        make="Mazda",
        model="RX-7",
        trim="Touring",
        mileage=80_000,
        location={"label": "Portland, OR 97202"},
    ) != NO_VIN_KEY


def test_bat_and_ebay_fixtures_count_as_one_comp_and_history_shows_the_drop():
    listings = [_listing("bat_e46.json"), _listing("ebay_e46.json")]
    prices = _prices("bat_e46_prices.json", "ebay_e46_prices.json")
    clusters = collapse_clusters(listings, prices)

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.vehicle_key == VIN_A
    assert cluster.match_method == "vin"
    assert set(cluster.listing_ids) == {"bd8f0e137da82645", "873b796649b684da"}
    assert cluster.facts.price == 31_200

    amounts = [point.amount for point in cluster.history.points]
    kinds = [point.kind for point in cluster.history.points]
    assert amounts == [34_800, 30_500, 33_900, 32_950, 31_200]
    assert kinds == ["asking", "bid", "asking", "asking", "asking"]
    asking = [point for point in cluster.history.points if point.kind == "asking"]
    assert asking[0].amount == 34_800
    assert asking[-1].amount == 31_200
    assert asking[-1].amount < asking[0].amount
    assert cluster.history.drop_count == 3
    assert cluster.history.first_price == 34_800
    assert cluster.history.last_price == 31_200
    assert cluster.history.days_on_market == 31
    assert cluster.history.change_pct == (31_200 - 34_800) / 34_800

    subject = _facts(listing_id="subject", price=20_000, mileage=62_140, vin=VIN_B)
    assessed = assess_price(subject, listings, prices)
    assert assessed.raw_count == 2
    assert assessed.cluster_count == 1
    assert assessed.comp_count == 1
    assert assessed.estimate == 31_200
    assert assessed.low == 31_200
    assert assessed.high == 31_200
    assert assessed.rating == "great"


def test_same_fuzzy_vehicle_key_collapses_and_the_next_mileage_band_does_not():
    base = _listing("no_vin.json")
    other = dict(base)
    other["source_url"] = "https://www.hemmings.com/listing/deaven-demo-1993-mazda-rx7-copy"
    other["price"] = 31_000
    assert len(collapse_clusters([base, other])) == 1
    assert collapse_clusters([base, other])[0].match_method == "fuzzy"
    assert collapse_clusters([base, other])[0].vehicle_key == NO_VIN_KEY

    later_band = dict(other)
    later_band["mileage"] = 80_000
    assert len(collapse_clusters([base, later_band])) == 2


def test_invalid_vin_fixture_collapses_on_the_fuzzy_key():
    invalid = _load("invalid_vin.json")
    first = {
        "vin": invalid["vin"],
        "year": invalid["year"],
        "make": invalid["make"],
        "model": invalid["model"],
        "trim": invalid["trim"],
        "mileage": invalid["mileage"],
        "price": 18_000,
        "currency": "USD",
        "location": invalid["location"],
        "source": "craigslist",
        "source_url": "https://example.com/listings/invalid-vin",
        "first_seen": "2026-05-01T00:00:00Z",
        "last_seen": "2026-05-02T00:00:00Z",
    }
    second = dict(first)
    second["source_url"] = "https://example.com/listings/invalid-vin-2"
    second["source"] = "ebay"
    second["price"] = 17_500
    clusters = collapse_clusters([first, second])
    assert len(clusters) == 1
    assert clusters[0].match_method == "fuzzy"
    assert clusters[0].vehicle_key == INVALID_VIN_KEY
    assert clusters[0].facts.vin is None


def test_assess_price_range_confidence_and_deduped_count():
    subject = _facts(listing_id="subject", price=30_000, vin=VIN_F)
    vins = [VIN_A, VIN_B, VIN_C, VIN_D, VIN_E]
    prices = [39_000, 40_000, 41_000, 42_000, 43_000]
    comps = [_facts(listing_id=f"c{i}", price=prices[i], vin=vins[i]) for i in range(5)]
    comps.append(_facts(listing_id="c0-ebay", price=39_500, vin=VIN_A))

    assessed = assess_price(subject, comps)
    assert assessed.raw_count == 6
    assert assessed.cluster_count == 5
    assert assessed.comp_count == 5
    assert assessed.cohort == "make_model_trim_year_region"
    assert assessed.confidence == "high"
    assert assessed.estimate == 41_000
    assert assessed.low == 40_000
    assert assessed.high == 42_000
    assert assessed.confidence_score == 0.607
    assert assessed.rating == "great"
    assert assessed.distance_band is None


def test_wider_spread_lowers_the_numeric_confidence():
    subject = _facts(listing_id="subject", price=60_000, vin=VIN_F)
    tight_prices = [39_000, 40_000, 41_000, 42_000, 43_000]
    wide_prices = [20_000, 40_000, 60_000, 80_000, 100_000]
    vins = [VIN_A, VIN_B, VIN_C, VIN_D, VIN_E]
    tight = assess_price(
        subject,
        [_facts(listing_id=f"t{i}", price=price, vin=vins[i]) for i, price in enumerate(tight_prices)],
    )
    wide = assess_price(
        subject,
        [_facts(listing_id=f"w{i}", price=price, vin=vins[i]) for i, price in enumerate(wide_prices)],
    )
    assert tight.comp_count == 5
    assert wide.comp_count == 5
    assert wide.low == 40_000
    assert wide.high == 80_000
    assert wide.estimate == 60_000
    assert wide.confidence_score == 0.438
    assert wide.confidence_score < tight.confidence_score


def test_single_comp_range_is_that_price_and_no_comps_are_unknown():
    subject = _facts(listing_id="subject", price=34_000, vin=VIN_F)
    one = assess_price(subject, [_facts(listing_id="only", price=40_000, vin=VIN_A)])
    assert one.estimate == 40_000
    assert one.low == 40_000
    assert one.high == 40_000
    assert one.comp_count == 1
    assert one.confidence == "low"
    assert one.confidence_score == 0.125
    assert one.rating == "great"

    none = assess_price(subject, [])
    assert none.estimate is None
    assert none.low is None
    assert none.high is None
    assert none.confidence_score == 0.0
    assert none.confidence == "insufficient"
    assert none.rating == "unknown"
    assert none.comp_count == 0


def test_subject_vehicle_key_is_not_used_as_its_own_comp():
    subject = _facts(listing_id="subject", price=30_000, vin=VIN_A)
    comps = [_facts(listing_id="relist", price=9_000, vin="1hgcm82633a004352")]
    comps.extend(_facts(listing_id=f"c{i}", price=40_000, vin=vin) for i, vin in enumerate((VIN_B, VIN_C, VIN_D)))
    assessed = assess_price(subject, comps)
    assert assessed.comp_count == 3
    assert assessed.estimate == 40_000


def test_lat_lon_distance_band_drops_comps_beyond_1000_miles():
    subject = _located("subject", VIN_F, 30_000, *AUSTIN)
    comps = [
        _located("near-a", VIN_A, 40_000, *AUSTIN),
        _located("near-b", VIN_B, 42_000, *AUSTIN),
        _located("near-c", VIN_C, 44_000, *AUSTIN),
        _located("dallas", VIN_D, 46_000, *DALLAS),
        _located("seattle", VIN_E, 90_000, *SEATTLE),
    ]
    assessed = assess_price(subject, comps)
    assert assessed.comp_count == 4
    assert assessed.estimate == 43_000
    assert assessed.distance_band == "regional"
    assert VIN_E not in assessed.vehicle_keys


def test_cluster_result_is_the_ui_contract_and_reuses_rate_deal():
    subject = _facts(listing_id="subject", price=30_000, vin=VIN_F)
    vins = [VIN_A, VIN_B, VIN_C, VIN_D, VIN_E]
    prices = [39_000, 40_000, 41_000, 42_000, 43_000]
    comps = [_facts(listing_id=f"c{i}", price=price, vin=vin) for i, (price, vin) in enumerate(zip(prices, vins))]
    comps.append(_facts(listing_id="c0-ebay", price=39_500, vin=VIN_A))

    result = cluster_result(subject, comps)
    assert [field.name for field in dataclasses.fields(ClusterResult)] == [
        "deal_score",
        "deal_rating",
        "estimate",
        "confidence",
        "comp_count",
    ]
    assert [field.name for field in dataclasses.fields(Estimate)] == ["low", "mid", "high"]
    assert result.estimate.mid == 41_000
    assert result.estimate.low == 40_000
    assert result.estimate.high == 42_000
    assert result.comp_count == 5
    assert result.confidence == 0.607
    assert result.deal_score == (41_000 - 30_000) / 41_000
    assert result.deal_rating == "great"
    assert rate_deal(30_000, 41_000) == "great"

    rich = _facts(listing_id="rich", price=12_000, vin=VIN_G)
    flat = [_facts(listing_id=f"f{i}", price=10_000, vin=vin) for i, vin in enumerate(vins)]
    over = cluster_result(rich, flat)
    assert rate_deal(12_000, 10_000) == "overpriced"
    assert over.deal_rating is None
    assert over.deal_score == (10_000 - 12_000) / 10_000
    assert over.estimate.mid == 10_000

    none = cluster_result(subject, [])
    assert none.deal_score is None
    assert none.deal_rating is None
    assert none.estimate == Estimate(None, None, None)
    assert none.confidence == 0.0
    assert none.comp_count == 0


def test_price_clusters_counts_the_bat_ebay_pair_once():
    others = [
        _facts(listing_id=f"c{i}", price=40_000, mileage=62_140, vin=vin)
        for i, vin in enumerate((VIN_B, VIN_C, VIN_D))
    ]
    listings = [_listing("bat_e46.json"), _listing("ebay_e46.json"), *others]
    prices = _prices("bat_e46_prices.json", "ebay_e46_prices.json")
    priced = price_clusters(listings, prices)
    shared = next(row for row in priced if row.vehicle_key == VIN_A)
    assert shared.match_method == "vin"
    assert set(shared.listing_ids) == {"bd8f0e137da82645", "873b796649b684da"}
    assert shared.result.comp_count == 3
    assert shared.result.estimate.mid == 40_000
    assert shared.result.deal_score == (40_000 - 31_200) / 40_000
    assert shared.result.deal_rating == "great"
    assert len(priced) == 4


def test_non_usd_observations_are_omitted():
    usd = _listing("bat_e46.json")
    eur = _listing("ebay_e46.json")
    eur["currency"] = "EUR"
    clusters = collapse_clusters([usd, eur])
    assert len(clusters) == 1
    assert clusters[0].facts.price == 31_200
    assert clusters[0].listing_ids == ("bd8f0e137da82645",)
