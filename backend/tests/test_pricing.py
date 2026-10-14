"""Synthetic comps only. No scraped listings."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.pricing.value import ListingFacts, estimate_value, facts_from_listing, rate_deal
from shared.schemas.deal import ListingData


def _car(**overrides) -> ListingFacts:
    fields = dict(
        listing_id="comp",
        price=40_000,
        make="BMW",
        model="M3",
        trim="Coupe",
        year=2003,
        mileage=60_000,
        region="TX",
    )
    fields.update(overrides)
    return ListingFacts(**fields)


def _cohort(n: int = 5, **overrides) -> list[ListingFacts]:
    prices = [39_000, 40_000, 41_000, 42_000, 43_000]
    return [
        _car(listing_id=f"c{i}", price=prices[i], **overrides)
        for i in range(n)
    ]


def test_facts_from_listing_reads_listing_data():
    listing = ListingData(
        title="2003 BMW M3 Coupe",
        price=34_000,
        mileage=62_000,
        year=2003,
        make="BMW",
        model="M3",
        trim="Coupe",
        vin="wbsbl93453jr00001",
        location="Austin, TX 78701",
        listing_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    facts = facts_from_listing(listing, "deal-1")
    assert facts.listing_id == "deal-1"
    assert facts.price == 34_000
    assert facts.make == "BMW"
    assert facts.model == "M3"
    assert facts.trim == "Coupe"
    assert facts.year == 2003
    assert facts.mileage == 62_000
    assert facts.region is None
    assert facts.vin == "WBSBL93453JR00001"


def test_region_comes_from_the_field_or_the_argument():
    austin = ListingData(title="M3", price=1, location="Austin, TX 78701")
    japan = ListingData(title="Supra", price=1, location="Japan")
    assert facts_from_listing(austin, "a").region is None
    assert facts_from_listing(austin, "a", region="ca").region == "CA"
    assert facts_from_listing(japan, "b").region is None


def test_builder_fields_win_when_present():
    from types import SimpleNamespace

    listing = SimpleNamespace(
        listing_id="bat:99",
        asking_price=31_000,
        price=99_000,
        trim="Coupe",
        trim_normalized="coupe",
        region="tx",
        make="BMW",
        model="M3",
        year=2003,
        mileage=10_000,
        vin=" abc ",
        location="Austin, TX 78701",
    )
    facts = facts_from_listing(listing, "fallback", region="CA")
    assert facts.listing_id == "bat:99"
    assert facts.price == 31_000
    assert facts.trim == "coupe"
    assert facts.region == "TX"


def test_estimate_is_median_of_tight_cohort():
    subject = _car(listing_id="subject", price=34_000)
    value = estimate_value(subject, _cohort())
    assert value.estimate == 41_000
    assert value.comp_count == 5
    assert value.cohort == "make_model_trim_year_region"
    assert value.confidence == "high"
    assert rate_deal(subject.price, value.estimate) == "great"


def test_subject_is_excluded_by_id_and_vin():
    subject = _car(listing_id="subject", price=34_000, vin="ABC123")
    comps = _cohort() + [
        _car(listing_id="subject", price=9_000),
        _car(listing_id="relist", price=9_000, vin="abc123"),
    ]
    value = estimate_value(subject, comps)
    assert value.comp_count == 5
    assert value.estimate == 41_000


def test_mileage_and_age_adjust_the_median():
    subject = _car(listing_id="subject", mileage=80_000, year=2001)
    comps = [_car(listing_id=f"c{i}", mileage=40_000, year=2004) for i in range(3)]
    # 4 * 1.5% mileage and 3 * 3% age: 0.94 * 0.91
    value = estimate_value(subject, comps)
    assert value.estimate == round(40_000 * 0.94 * 0.91, 2)
    assert value.comp_count == 3


def test_adjustment_is_clamped():
    subject = _car(listing_id="subject", mileage=400_000)
    comps = [_car(listing_id=f"c{i}", mileage=10_000) for i in range(3)]
    value = estimate_value(subject, comps)
    assert value.estimate == round(40_000 * 0.45, 2)


def test_thin_region_falls_back_to_national_trim_cohort():
    subject = _car(listing_id="subject", region="TX")
    comps = [_car(listing_id="local", region="TX", price=50_000)]
    comps += [_car(listing_id=f"ca{i}", region="CA", price=40_000) for i in range(4)]
    value = estimate_value(subject, comps)
    assert value.cohort == "make_model_trim_year"
    assert value.comp_count == 5
    assert value.estimate == 40_000
    assert value.confidence == "medium"


def test_no_comps_is_insufficient_and_unknown():
    subject = _car(listing_id="subject", make="Honda", model="S2000")
    value = estimate_value(subject, _cohort())
    assert value.estimate is None
    assert value.confidence == "insufficient"
    assert value.comp_count == 0
    assert value.cohort == "none"
    assert rate_deal(subject.price, value.estimate) == "unknown"


def test_match_is_case_insensitive():
    subject = _car(listing_id="subject", make="bmw", model="m3", trim="coupe", region="tx")
    value = estimate_value(subject, _cohort(3))
    assert value.comp_count == 3
    assert value.cohort == "make_model_trim_year_region"
    assert value.confidence == "medium"


def test_rating_thresholds():
    assert rate_deal(8_500, 10_000) == "great"       # -15%
    assert rate_deal(8_501, 10_000) == "good"
    assert rate_deal(9_500, 10_000) == "good"        # -5%
    assert rate_deal(10_500, 10_000) == "fair"       # +5%
    assert rate_deal(11_500, 10_000) == "high"       # +15%
    assert rate_deal(11_501, 10_000) == "overpriced"
    assert rate_deal(8_300, 10_000, great=-0.20) == "good"
    with pytest.raises(ValueError):
        rate_deal(1, 1, great=0.1, good=0.0, fair=0.2, high=0.3)
