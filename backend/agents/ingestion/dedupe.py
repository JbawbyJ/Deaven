"""Group normalized listings with the market vehicle_key.

vehicle_key already calls vin_key and, when that returns None, the fuzzy
hash (year, make, model, trim, mileage band, ZIP from ListingLocation.label).
This module does not rebuild either key. Clusters are VehicleCluster.
Each listing also emits one PriceObservation for its current price.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.schemas.listing import MatchMethod, NormalizedListing
from shared.schemas.market import PriceKind, PriceObservation, VehicleCluster, vehicle_key
from shared.vin import vin_key


@dataclass(frozen=True)
class DedupeResult:
    clusters: list[VehicleCluster]
    prices: list[PriceObservation]


def dedupe(listings: list[NormalizedListing]) -> DedupeResult:
    order: list[str] = []
    groups: dict[str, list[NormalizedListing]] = {}
    for listing in listings:
        key = vehicle_key(listing)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(listing)

    clusters: list[VehicleCluster] = []
    prices: list[PriceObservation] = []
    for key in order:
        group = groups[key]
        method = (
            MatchMethod.VIN
            if any(_grouped_by_vin(item, key) for item in group)
            else MatchMethod.FUZZY
        )
        clusters.append(
            VehicleCluster(
                vehicle_key=key,
                listing_ids=[item.observation_id for item in group],
                match_method=method,
            )
        )
        prices.extend(price_points(group))
    return DedupeResult(clusters=clusters, prices=prices)


def price_points(
    listings: list[NormalizedListing],
    *,
    kind: PriceKind = PriceKind.ASKING,
) -> list[PriceObservation]:
    """One current price per listing. Asking price is the listing's price field."""
    return [
        PriceObservation(
            listing_id=item.observation_id,
            observed_at=item.provenance.fetched_at,
            amount=item.price,
            currency=item.currency,
            kind=kind,
        )
        for item in listings
    ]


def _grouped_by_vin(listing: NormalizedListing, key: str) -> bool:
    if not listing.vin:
        return False
    return vin_key(listing.vin) == key
