"""
Side-by-side comparison of listings already priced by this lane.

No HTTP route. Builder 3 owns the screen and can call compare directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.pricing.history import PriceHistorySummary, PriceObservation, summarize_history
from backend.pricing.value import ListingFacts, estimate_value, rate_deal

_RATING_RANK = {
    "great": 0,
    "good": 1,
    "fair": 2,
    "high": 3,
    "overpriced": 4,
    "unknown": 5,
}


@dataclass(frozen=True)
class ComparisonRow:
    listing_id: str
    year: int | None
    make: str | None
    model: str | None
    trim: str | None
    mileage: int | None
    region: str | None
    asking_price: float
    estimate: float | None
    confidence: str
    deal_rating: str
    price_history: PriceHistorySummary | None
    delta_vs_cheapest: float
    delta_vs_estimate: float | None
    delta_vs_estimate_pct: float | None
    best_value: bool


def compare(
    listings: list[ListingFacts],
    comps: list[ListingFacts] | None = None,
    *,
    histories: dict[str, list[PriceObservation]] | None = None,
    as_of: datetime | None = None,
) -> list[ComparisonRow]:
    """One row per listing, in input order.

    comps defaults to the listings themselves. Each listing is dropped from
    its own comp set by id and VIN. histories maps listing_id to observations;
    a missing or empty list leaves price_history null. Exactly one row has
    best_value: best deal rating, then lowest asking price, then earlier input.
    Deltas are dollars. delta_vs_estimate_pct is a fraction (0.10 is 10% above).
    """
    if not listings:
        raise ValueError("compare requires at least one listing")
    ids = [item.listing_id for item in listings]
    if len(ids) != len(set(ids)):
        raise ValueError("listing_id values must be unique")

    market = list(listings if comps is None else comps)
    histories = histories or {}
    cheapest = min(item.price for item in listings)
    drafted = []
    for index, item in enumerate(listings):
        value = estimate_value(item, market)
        rating = rate_deal(item.price, value.estimate)
        observations = histories.get(item.listing_id) or []
        history = (
            summarize_history(item.listing_id, observations, as_of=as_of)
            if observations
            else None
        )
        if value.estimate:
            delta = round(item.price - value.estimate, 2)
            delta_pct = round(delta / value.estimate, 4)
        else:
            delta = None
            delta_pct = None
        drafted.append((index, item, value, rating, history, delta, delta_pct))

    best_index = min(
        drafted,
        key=lambda row: (_RATING_RANK.get(row[3], 5), row[1].price, row[0]),
    )[0]
    return [
        ComparisonRow(
            listing_id=item.listing_id,
            year=item.year,
            make=item.make,
            model=item.model,
            trim=item.trim,
            mileage=item.mileage,
            region=item.region,
            asking_price=item.price,
            estimate=value.estimate,
            confidence=value.confidence,
            deal_rating=rating,
            price_history=history,
            delta_vs_cheapest=round(item.price - cheapest, 2),
            delta_vs_estimate=delta,
            delta_vs_estimate_pct=delta_pct,
            best_value=index == best_index,
        )
        for index, item, value, rating, history, delta, delta_pct in drafted
    ]
