"""
Fair-price estimate and deal rating.

Reads shared.schemas.deal.ListingData through facts_from_listing.
That function is the swap point for Builder's listing schema
(agent/builder/deaven-ingestion), which was not published yet.
This module does not store a second listing schema and does not scrape.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from shared.schemas.deal import ListingData

# Cohort must reach this many comps before a wider cohort is used.
MIN_COMPS = 3
# Same mileage slope as the live valuation agent: 1.5% per 10k miles.
MILEAGE_RATE_PER_10K = 0.015
AGE_RATE_PER_YEAR = 0.03
ADJUSTMENT_FLOOR = 0.45
ADJUSTMENT_CEILING = 1.80
YEAR_WINDOW_TIGHT = 1
YEAR_WINDOW_BROAD = 2

# Asking price vs estimate: (price - estimate) / estimate.
# A listing at or under the bound takes that rating.
GREAT_MAX_DELTA = -0.15
GOOD_MAX_DELTA = -0.05
FAIR_MAX_DELTA = 0.05
HIGH_MAX_DELTA = 0.15

# name, year window (None = any year), require trim, require region
_COHORTS = (
    ("make_model_trim_year_region", YEAR_WINDOW_TIGHT, True, True),
    ("make_model_trim_year", YEAR_WINDOW_TIGHT, True, False),
    ("make_model_year", YEAR_WINDOW_BROAD, False, False),
    ("make_model", None, False, False),
)


@dataclass(frozen=True)
class ListingFacts:
    """Fields pricing reads. Built from ListingData; not an ingestion record."""

    listing_id: str
    price: float
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    year: int | None = None
    mileage: int | None = None
    region: str | None = None
    vin: str | None = None


@dataclass(frozen=True)
class MarketValue:
    estimate: float | None
    confidence: str
    comp_count: int
    cohort: str


def facts_from_listing(
    listing: ListingData,
    listing_id: str,
    *,
    region: str | None = None,
) -> ListingFacts:
    """Copy the pricing fields off a ListingData record.

    Region comes from the override, otherwise from a state code in
    listing.location. Zip is not a ListingData field.
    """
    resolved = region or _region_from_location(listing.location)
    return ListingFacts(
        listing_id=listing_id,
        price=float(listing.price),
        make=listing.make,
        model=listing.model,
        trim=listing.trim,
        year=listing.year,
        mileage=listing.mileage,
        region=_canon_region(resolved),
        vin=(listing.vin or "").strip().upper() or None,
    )


def estimate_value(
    subject: ListingFacts,
    comps: list[ListingFacts],
    *,
    min_comps: int = MIN_COMPS,
    mileage_rate: float = MILEAGE_RATE_PER_10K,
    age_rate: float = AGE_RATE_PER_YEAR,
) -> MarketValue:
    """Median of mileage- and age-adjusted comps in the narrowest viable cohort."""
    matched, cohort = _select_cohort(subject, comps, min_comps)
    if not matched:
        return MarketValue(None, "insufficient", 0, "none")
    adjusted = [_adjust(subject, comp, mileage_rate, age_rate) for comp in matched]
    return MarketValue(
        estimate=round(statistics.median(adjusted), 2),
        confidence=_confidence(cohort, len(matched)),
        comp_count=len(matched),
        cohort=cohort,
    )


def matched_adjusted_prices(
    subject: ListingFacts,
    comps: list[ListingFacts],
    *,
    min_comps: int = MIN_COMPS,
    mileage_rate: float = MILEAGE_RATE_PER_10K,
    age_rate: float = AGE_RATE_PER_YEAR,
) -> tuple[list[ListingFacts], list[float], str]:
    """Same cohort and adjustments as estimate_value, with the adjusted prices kept."""
    matched, cohort = _select_cohort(subject, comps, min_comps)
    if not matched:
        return [], [], "none"
    adjusted = [_adjust(subject, comp, mileage_rate, age_rate) for comp in matched]
    return matched, adjusted, cohort


def rate_deal(
    price: float,
    estimate: float | None,
    *,
    great: float = GREAT_MAX_DELTA,
    good: float = GOOD_MAX_DELTA,
    fair: float = FAIR_MAX_DELTA,
    high: float = HIGH_MAX_DELTA,
) -> str:
    """great / good / fair / high / overpriced, or unknown when there is no estimate."""
    bounds = (great, good, fair, high)
    if list(bounds) != sorted(bounds) or len(set(bounds)) != 4:
        raise ValueError("rating thresholds must be strictly increasing")
    if estimate is None or estimate <= 0:
        return "unknown"
    delta = (price - estimate) / estimate
    if delta <= great:
        return "great"
    if delta <= good:
        return "good"
    if delta <= fair:
        return "fair"
    if delta <= high:
        return "high"
    return "overpriced"


def _select_cohort(
    subject: ListingFacts,
    comps: list[ListingFacts],
    min_comps: int,
) -> tuple[list[ListingFacts], str]:
    if not _token(subject.make) or not _token(subject.model):
        return [], "none"
    pool = [comp for comp in comps if comp.price > 0 and not _same_car(subject, comp)]
    best: list[ListingFacts] = []
    best_name = "none"
    first_name = None
    for name, window, need_trim, need_region in _COHORTS:
        if not _applicable(subject, window, need_trim, need_region):
            continue
        if first_name is None:
            first_name = name
        matched = [
            comp
            for comp in pool
            if _in_cohort(subject, comp, window, need_trim, need_region)
        ]
        if len(matched) >= min_comps:
            return matched, name
        if len(matched) > len(best):
            best, best_name = matched, name
    return best, best_name if best else "none"


def _applicable(subject: ListingFacts, window: int | None, need_trim: bool, need_region: bool) -> bool:
    if need_trim and not _token(subject.trim):
        return False
    if need_region and not _token(subject.region):
        return False
    if window is not None and subject.year is None:
        return False
    return True


def _in_cohort(
    subject: ListingFacts,
    comp: ListingFacts,
    window: int | None,
    need_trim: bool,
    need_region: bool,
) -> bool:
    if _token(subject.make) != _token(comp.make) or _token(subject.model) != _token(comp.model):
        return False
    if need_trim and _token(subject.trim) != _token(comp.trim):
        return False
    if need_region and _token(subject.region) != _token(comp.region):
        return False
    if window is not None:
        if subject.year is None or comp.year is None:
            return False
        if abs(subject.year - comp.year) > window:
            return False
    return True


def _adjust(subject: ListingFacts, comp: ListingFacts, mileage_rate: float, age_rate: float) -> float:
    factor = 1.0
    if subject.mileage is not None and comp.mileage is not None:
        factor *= 1 - ((subject.mileage - comp.mileage) / 10_000) * mileage_rate
    if subject.year is not None and comp.year is not None:
        factor *= 1 - (comp.year - subject.year) * age_rate
    return comp.price * min(ADJUSTMENT_CEILING, max(ADJUSTMENT_FLOOR, factor))


def _confidence(cohort: str, count: int) -> str:
    if count <= 0 or cohort == "none":
        return "insufficient"
    if count < MIN_COMPS:
        return "low"
    if cohort == "make_model_trim_year_region":
        return "high" if count >= 5 else "medium"
    if cohort == "make_model_trim_year" and count >= 5:
        return "medium"
    return "low"


def _same_car(subject: ListingFacts, comp: ListingFacts) -> bool:
    if subject.listing_id and subject.listing_id == comp.listing_id:
        return True
    vin_s = (subject.vin or "").strip().upper()
    vin_c = (comp.vin or "").strip().upper()
    return bool(vin_s and vin_s == vin_c)


def _token(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _canon_region(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(value.split())
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return text or None


def _region_from_location(location: str | None) -> str | None:
    if not location:
        return None
    parts = [part.strip() for part in location.split(",") if part.strip()]
    tokens = (parts[-1] if parts else location).split()
    while tokens and tokens[-1][0].isdigit():
        tokens.pop()
    if not tokens:
        return None
    if len(tokens[-1]) == 2 and tokens[-1].isalpha():
        return tokens[-1].upper()
    return " ".join(tokens)
