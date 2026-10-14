"""Synthetic listings only. No scraped data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.pricing.compare import compare
from backend.pricing.history import PriceObservation
from backend.pricing.value import ListingFacts


def _car(**overrides) -> ListingFacts:
    fields = dict(
        listing_id="car",
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


def _comps() -> list[ListingFacts]:
    prices = [39_000, 40_000, 41_000, 42_000, 43_000]
    return [_car(listing_id=f"comp-{i}", price=price) for i, price in enumerate(prices)]


def _at(day: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)


def test_compare_flags_best_rating_not_the_cheapest_price():
    listings = [
        _car(listing_id="honda", make="Honda", model="S2000", trim=None, price=15_000),
        _car(listing_id="deal", price=32_000),
        _car(listing_id="pricier", price=34_000),
    ]
    rows = compare(
        listings,
        _comps(),
        histories={
            "deal": [
                PriceObservation("deal", 45_000, _at(0)),
                PriceObservation("deal", 32_000, _at(10)),
            ]
        },
    )
    assert [row.listing_id for row in rows] == ["honda", "deal", "pricier"]
    assert [row.best_value for row in rows] == [False, True, False]

    honda, deal, pricier = rows
    assert honda.asking_price == 15_000
    assert honda.estimate is None
    assert honda.confidence == "insufficient"
    assert honda.deal_rating == "unknown"
    assert honda.delta_vs_cheapest == 0
    assert honda.delta_vs_estimate is None
    assert honda.delta_vs_estimate_pct is None
    assert honda.price_history is None
    assert honda.year == 2003 and honda.make == "Honda" and honda.region == "TX"

    assert deal.estimate == 41_000
    assert deal.confidence == "high"
    assert deal.deal_rating == "great"
    assert deal.mileage == 60_000 and deal.trim == "Coupe"
    assert deal.delta_vs_cheapest == 17_000
    assert deal.delta_vs_estimate == -9_000
    assert deal.delta_vs_estimate_pct == round(-9_000 / 41_000, 4)
    assert deal.price_history is not None
    assert deal.price_history.current_price == 32_000
    assert deal.price_history.first_price == 45_000
    assert deal.price_history.trend == "down"
    assert deal.price_history.days_on_market == 10

    assert pricier.deal_rating == "great"
    assert pricier.delta_vs_cheapest == 19_000
    assert pricier.delta_vs_estimate == -7_000
    assert pricier.price_history is None


def test_omitted_comps_use_the_other_listings():
    listings = [
        _car(listing_id="a", price=39_000),
        _car(listing_id="b", price=40_000),
        _car(listing_id="c", price=41_000),
        _car(listing_id="d", price=42_000),
    ]
    rows = compare(listings)
    assert rows[0].estimate == 41_000
    assert rows[0].confidence == "medium"
    assert rows[0].deal_rating == "fair"
    assert rows[0].best_value is True
    assert sum(row.best_value for row in rows) == 1


def test_compare_rejects_empty_and_duplicate_ids():
    with pytest.raises(ValueError):
        compare([])
    with pytest.raises(ValueError):
        compare([_car(listing_id="same"), _car(listing_id="same", price=1)])
