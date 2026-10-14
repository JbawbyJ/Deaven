"""
Group ListingData rows that are the same vehicle.

Exact key: a check-digit-valid VIN. Those rows merge even when price or
place differ.

Fuzzy fallback, only when at least one side has no VIN: same year, make,
and model; trim_normalized must not conflict; mileage and asking price
inside tolerance; same ZIP if both have one, otherwise same region.
The source rows are kept. Each row in a cluster gets the same canonical_id.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from itertools import combinations

from shared.schemas.deal import ListingData, normalize_trim
from shared.vin import is_valid_vin


@dataclass(frozen=True)
class DedupeConfig:
    mileage_abs: int = 500
    mileage_pct: float = 0.02
    price_abs: float = 500.0
    price_pct: float = 0.05


@dataclass(frozen=True)
class DedupeCluster:
    canonical_id: str
    records: list[ListingData]


def dedupe(
    listings: list[ListingData],
    config: DedupeConfig | None = None,
) -> list[DedupeCluster]:
    cfg = config or DedupeConfig()
    parent = list(range(len(listings)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    by_vin: dict[str, list[int]] = {}
    for index, listing in enumerate(listings):
        if listing.vin and is_valid_vin(listing.vin):
            by_vin.setdefault(listing.vin, []).append(index)
    for indexes in by_vin.values():
        for other in indexes[1:]:
            union(indexes[0], other)

    buckets: dict[tuple[int, str, str], list[int]] = {}
    for index, listing in enumerate(listings):
        if listing.year is None:
            continue
        make = normalize_trim(listing.make)
        model = normalize_trim(listing.model)
        if not make or not model:
            continue
        buckets.setdefault((listing.year, make, model), []).append(index)

    for indexes in buckets.values():
        for left, right in combinations(indexes, 2):
            if find(left) == find(right):
                continue
            if _fuzzy_match(listings[left], listings[right], cfg):
                union(left, right)

    groups: dict[int, list[ListingData]] = {}
    for index, listing in enumerate(listings):
        groups.setdefault(find(index), []).append(listing)

    clusters: list[DedupeCluster] = []
    for records in groups.values():
        ordered = sorted(records, key=_record_key)
        canonical_id = _canonical_id(ordered)
        for record in ordered:
            record.canonical_id = canonical_id
        clusters.append(DedupeCluster(canonical_id=canonical_id, records=ordered))
    clusters.sort(key=lambda cluster: cluster.canonical_id)
    return clusters


def _fuzzy_match(left: ListingData, right: ListingData, cfg: DedupeConfig) -> bool:
    if left.vin and right.vin:
        return False
    if left.year is None or right.year is None or left.year != right.year:
        return False
    if not _same_token(left.make, right.make) or not _same_token(left.model, right.model):
        return False
    if left.trim_normalized and right.trim_normalized and left.trim_normalized != right.trim_normalized:
        return False
    if not _within(left.mileage, right.mileage, cfg.mileage_abs, cfg.mileage_pct):
        return False
    if not _within(left.price, right.price, cfg.price_abs, cfg.price_pct):
        return False
    return _place_ok(left, right)


def _same_token(left: str | None, right: str | None) -> bool:
    a = normalize_trim(left)
    b = normalize_trim(right)
    return bool(a and b and a == b)


def _within(left: float | int | None, right: float | int | None, absolute: float, percent: float) -> bool:
    if left is None or right is None:
        return True
    gap = abs(float(left) - float(right))
    baseline = min(abs(float(left)), abs(float(right)))
    return gap <= max(absolute, percent * baseline)


def _place_ok(left: ListingData, right: ListingData) -> bool:
    left_zip = _zip5(left.zip)
    right_zip = _zip5(right.zip)
    if left_zip and right_zip:
        return left_zip == right_zip
    left_region = (left.region or "").strip().upper()
    right_region = (right.region or "").strip().upper()
    if left_region and right_region:
        return left_region == right_region
    return False


def _zip5(value: str | None) -> str:
    if not value:
        return ""
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:5] if len(digits) >= 5 else ""


def _record_key(listing: ListingData) -> str:
    return listing.listing_id or f"{listing.title}|{listing.price}|{listing.zip or ''}"


def _canonical_id(records: list[ListingData]) -> str:
    vins = sorted({record.vin for record in records if record.vin})
    if vins:
        return f"vin:{vins[0]}"
    raw = "|".join(_record_key(record) for record in records)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"fuzzy:{digest}"
