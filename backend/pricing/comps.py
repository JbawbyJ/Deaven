"""Collapse cross-listed cars, then price the deduped set.

Identity is `vehicle_key` from the listing model (a VIN, otherwise that
model's fuzzy hash). This module does not invent a second fuzzy key.
Latitude and longitude are used only as distance bands, because
ListingLocation has no zip field.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from backend.pricing.adapter import ListingView, PriceView, read_listing, read_price, vin_key
from backend.pricing.value import (
    ListingFacts,
    estimate_value,
    matched_adjusted_prices,
    rate_deal,
)

# Comp must sit inside this radius when both sides have coordinates.
EXTENDED_MILES = 1_000.0
METRO_MILES = 50.0
REGIONAL_MILES = 250.0

# Numeric confidence. Count caps the score and saturates at 8 comps.
# quality_term = 0.40 + 0.30 * spread + 0.30 * cohort match.
# Spread hits 0 when the interquartile range is half the median.
_COUNT_SATURATION = 8
_SPREAD_WIDTH = 0.50
_COHORT_QUALITY = {
    "make_model_trim_year_region": 1.0,
    "make_model_trim_year": 0.80,
    "make_model_year": 0.55,
    "make_model": 0.35,
    "none": 0.0,
}


@dataclass(frozen=True)
class PricePoint:
    listing_id: str
    observed_at: datetime
    amount: float
    currency: str
    kind: str
    source: str | None = None


@dataclass(frozen=True)
class PriceHistory:
    """Asking series from PriceObservation rows, oldest first."""

    points: tuple[PricePoint, ...]
    drop_count: int
    days_on_market: int | None
    first_price: float | None
    last_price: float | None
    change_pct: float | None


@dataclass(frozen=True)
class CollapsedComp:
    """One vehicle after vehicle_key collapse. Field names match VehicleCluster."""

    vehicle_key: str
    listing_ids: tuple[str, ...]
    match_method: str
    facts: ListingFacts
    history: PriceHistory
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class Estimate:
    """Point and range in the listing currency. No FX."""

    low: float | None
    mid: float | None
    high: float | None


@dataclass(frozen=True)
class ClusterResult:
    """Sort contract for one VehicleCluster. These five fields only.

    deal_score is (estimate - asking) / estimate. Positive means the ask is
    below the estimate. None when there is no estimate.
    deal_rating reuses rate_deal. great/good/fair/high pass through,
    overpriced maps to high, and only unknown maps to null.
    """

    deal_score: float | None
    deal_rating: str | None
    estimate: Estimate
    confidence: float
    comp_count: int


@dataclass(frozen=True)
class PricedCluster:
    """VehicleCluster identity plus the UI result. Sort on result.deal_score."""

    vehicle_key: str
    listing_ids: tuple[str, ...]
    match_method: str
    result: ClusterResult


_UI_RATINGS = frozenset({"great", "good", "fair", "high"})


def _ui_rating(legacy: str) -> str | None:
    """Map rate_deal onto great/good/fair/high/null. overpriced becomes high."""
    if legacy == "overpriced":
        return "high"
    if legacy in _UI_RATINGS:
        return legacy
    return None


@dataclass(frozen=True)
class PriceAssessment:
    estimate: float | None
    low: float | None
    high: float | None
    confidence_score: float
    confidence: str
    rating: str
    comp_count: int
    cohort: str
    raw_count: int
    cluster_count: int
    vehicle_keys: tuple[str, ...]
    distance_band: str | None


def collapse_clusters(
    listings: Sequence[Any],
    prices: Sequence[Any] | None = None,
) -> list[CollapsedComp]:
    """One comp per vehicle_key. Cross-listed rows that share a key count once."""
    grouped: dict[str, list[ListingView]] = {}
    order: list[str] = []
    for index, record in enumerate(listings):
        view = read_listing(record, index)
        if view is None:
            continue
        if view.vehicle_key not in grouped:
            order.append(view.vehicle_key)
            grouped[view.vehicle_key] = []
        grouped[view.vehicle_key].append(view)
    observations = _read_prices(prices)
    return [_collapse(key, grouped[key], observations) for key in order]


def assess_price(
    subject: Any,
    comps: Sequence[Any],
    prices: Sequence[Any] | None = None,
) -> PriceAssessment:
    """Deduped estimate, p25/p75 range, 0–1 confidence, and the #2 deal rating."""
    clusters = collapse_clusters(comps, prices)
    return _assess(read_listing(subject, index=-1), clusters, raw_count=len(comps))


def cluster_result(
    subject: Any,
    comps: Sequence[Any],
    prices: Sequence[Any] | None = None,
) -> ClusterResult:
    """UI result for one vehicle, scored against the other clusters."""
    subject_view = read_listing(subject, index=-1)
    asking = subject_view.price if subject_view is not None else 0.0
    return _cluster_result(assess_price(subject, comps, prices), asking)


def price_clusters(
    listings: Sequence[Any],
    prices: Sequence[Any] | None = None,
) -> list[PricedCluster]:
    """One result per VehicleCluster. Each car is scored against the other clusters."""
    clusters = collapse_clusters(listings, prices)
    priced: list[PricedCluster] = []
    for cluster in clusters:
        others = [other for other in clusters if other.vehicle_key != cluster.vehicle_key]
        assessment = _assess(_view_from_cluster(cluster), others, raw_count=len(listings))
        priced.append(
            PricedCluster(
                vehicle_key=cluster.vehicle_key,
                listing_ids=cluster.listing_ids,
                match_method=cluster.match_method,
                result=_cluster_result(assessment, cluster.facts.price),
            )
        )
    return priced


def _assess(
    subject_view: ListingView | None,
    clusters: list[CollapsedComp],
    raw_count: int,
) -> PriceAssessment:
    subject_facts = _facts(subject_view) if subject_view is not None else ListingFacts(
        listing_id="subject",
        price=0,
    )
    kept = [cluster for cluster in clusters if _keep(subject_view, cluster)]
    comp_facts = [cluster.facts for cluster in kept]
    market = estimate_value(subject_facts, comp_facts)
    matched, adjusted, _cohort = matched_adjusted_prices(subject_facts, comp_facts)
    low, high = _range(adjusted)
    keys = tuple(comp.listing_id for comp in matched)
    return PriceAssessment(
        estimate=market.estimate,
        low=low,
        high=high,
        confidence_score=_confidence_score(adjusted, market.cohort),
        confidence=market.confidence,
        rating=rate_deal(subject_facts.price, market.estimate),
        comp_count=market.comp_count,
        cohort=market.cohort,
        raw_count=raw_count,
        cluster_count=len(clusters),
        vehicle_keys=keys,
        distance_band=_distance_band(subject_view, kept, keys),
    )


def _cluster_result(assessment: PriceAssessment, asking: float) -> ClusterResult:
    mid = assessment.estimate
    score = None if mid is None or mid <= 0 else (mid - asking) / mid
    rating = _ui_rating(assessment.rating)
    return ClusterResult(
        deal_score=score,
        deal_rating=rating,
        estimate=Estimate(low=assessment.low, mid=mid, high=assessment.high),
        confidence=assessment.confidence_score,
        comp_count=assessment.comp_count,
    )


def _view_from_cluster(cluster: CollapsedComp) -> ListingView:
    facts = cluster.facts
    return ListingView(
        listing_id=cluster.listing_ids[0] if cluster.listing_ids else cluster.vehicle_key,
        price=facts.price,
        make=facts.make,
        model=facts.model,
        trim=facts.trim,
        year=facts.year,
        mileage=facts.mileage,
        region=facts.region,
        vin=facts.vin,
        label=None,
        latitude=cluster.latitude,
        longitude=cluster.longitude,
        currency="USD",
        source=None,
        first_seen=None,
        last_seen=None,
        vehicle_key=cluster.vehicle_key,
        input_index=-1,
    )


def _collapse(key: str, members: list[ListingView], prices: list[PriceView]) -> CollapsedComp:
    ids = tuple(member.listing_id for member in members)
    id_set = set(ids)
    rows = [row for row in prices if row.listing_id in id_set]
    sources = {member.listing_id: member.source for member in members}
    history = _history(rows, sources, members)
    rep, price = _representative(members, rows)
    method = "fuzzy"
    normalized = None
    for member in members:
        candidate = vin_key(member.vin or "")
        if candidate is not None and candidate == key:
            method = "vin"
            normalized = candidate
            break
    return CollapsedComp(
        vehicle_key=key,
        listing_ids=ids,
        match_method=method,
        facts=_facts(rep, price=price, vin=normalized if method == "vin" else None),
        history=history,
        latitude=rep.latitude,
        longitude=rep.longitude,
    )


def _representative(members: list[ListingView], prices: list[PriceView]) -> tuple[ListingView, float]:
    asking = [row for row in prices if row.kind == "asking"]
    if asking:
        latest = max(asking, key=lambda row: (row.observed_at, row.listing_id))
        rep = next((member for member in members if member.listing_id == latest.listing_id), members[-1])
        return rep, latest.amount
    rep = max(members, key=_recency)
    return rep, rep.price


def _recency(member: ListingView) -> tuple[datetime, int]:
    stamp = member.last_seen or member.first_seen or datetime.min.replace(tzinfo=timezone.utc)
    return stamp, member.input_index


def _history(
    prices: list[PriceView],
    sources: dict[str, str | None],
    members: list[ListingView],
) -> PriceHistory:
    points = tuple(
        PricePoint(
            listing_id=row.listing_id,
            observed_at=row.observed_at,
            amount=row.amount,
            currency=row.currency,
            kind=row.kind,
            source=sources.get(row.listing_id),
        )
        for row in sorted(prices, key=lambda row: (row.observed_at, row.listing_id))
    )
    asking = [point for point in points if point.kind == "asking"]
    drops = 0
    for earlier, later in zip(asking, asking[1:]):
        if later.amount < earlier.amount:
            drops += 1
    first_price = asking[0].amount if asking else None
    last_price = asking[-1].amount if asking else None
    change = None
    if first_price not in (None, 0) and last_price is not None:
        change = (last_price - first_price) / first_price
    start, end = _span(points, members)
    days = (end - start).days if start is not None and end is not None else None
    return PriceHistory(
        points=points,
        drop_count=drops,
        days_on_market=days,
        first_price=first_price,
        last_price=last_price,
        change_pct=change,
    )


def _span(
    points: tuple[PricePoint, ...],
    members: list[ListingView],
) -> tuple[datetime | None, datetime | None]:
    stamps: list[datetime] = [point.observed_at for point in points]
    for member in members:
        if member.first_seen is not None:
            stamps.append(member.first_seen)
        if member.last_seen is not None:
            stamps.append(member.last_seen)
    if not stamps:
        return None, None
    return min(stamps), max(stamps)


_MISSING = object()


def _facts(view: ListingView, *, price: float | None = None, vin: Any = _MISSING) -> ListingFacts:
    if vin is _MISSING:
        resolved_vin = vin_key(view.vin or "")
    else:
        resolved_vin = vin
    return ListingFacts(
        listing_id=view.vehicle_key,
        price=view.price if price is None else price,
        make=view.make,
        model=view.model,
        trim=view.trim,
        year=view.year,
        mileage=view.mileage,
        region=view.region,
        vin=resolved_vin,
    )


def _keep(subject: ListingView | None, cluster: CollapsedComp) -> bool:
    if subject is None:
        return True
    if cluster.vehicle_key == subject.vehicle_key:
        return False
    if subject.listing_id and subject.listing_id in cluster.listing_ids:
        return False
    return _within_extended(subject, cluster)


def _within_extended(subject: ListingView, cluster: CollapsedComp) -> bool:
    miles = _miles(subject.latitude, subject.longitude, cluster.latitude, cluster.longitude)
    if miles is None:
        return True
    return miles <= EXTENDED_MILES


def _distance_band(
    subject: ListingView | None,
    clusters: list[CollapsedComp],
    used_keys: tuple[str, ...],
) -> str | None:
    if subject is None or subject.latitude is None or subject.longitude is None:
        return None
    used = set(used_keys)
    distances = [
        _miles(subject.latitude, subject.longitude, cluster.latitude, cluster.longitude)
        for cluster in clusters
        if cluster.vehicle_key in used
    ]
    known = [miles for miles in distances if miles is not None]
    if not known:
        return None
    return _band(max(known))


def _band(miles: float) -> str:
    if miles <= METRO_MILES:
        return "metro"
    if miles <= REGIONAL_MILES:
        return "regional"
    return "extended"


def _miles(
    lat1: float | None,
    lon1: float | None,
    lat2: float | None,
    lon2: float | None,
) -> float | None:
    if None in (lat1, lon1, lat2, lon2):
        return None
    return _haversine(lat1, lon1, lat2, lon2)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.7613
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _range(adjusted: list[float]) -> tuple[float | None, float | None]:
    if not adjusted:
        return None, None
    return round(_percentile(adjusted, 0.25), 2), round(_percentile(adjusted, 0.75), 2)


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = fraction * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _confidence_score(adjusted: list[float], cohort: str) -> float:
    if not adjusted or cohort == "none":
        return 0.0
    count_factor = min(1.0, len(adjusted) / _COUNT_SATURATION)
    median = sorted(adjusted)[len(adjusted) // 2]
    if len(adjusted) % 2 == 0:
        median = (sorted(adjusted)[len(adjusted) // 2 - 1] + median) / 2
    if median <= 0:
        spread_factor = 0.0
    else:
        iqr = _percentile(adjusted, 0.75) - _percentile(adjusted, 0.25)
        spread_factor = max(0.0, 1.0 - (iqr / median) / _SPREAD_WIDTH)
    quality = _COHORT_QUALITY.get(cohort, 0.0)
    term = 0.40 + 0.30 * spread_factor + 0.30 * quality
    return round(min(1.0, max(0.0, count_factor * term)), 3)


def _read_prices(prices: Sequence[Any] | None) -> list[PriceView]:
    rows: list[PriceView] = []
    for record in prices or []:
        view = read_price(record)
        if view is not None:
            rows.append(view)
    return rows
