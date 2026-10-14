"""GET /api/listings/search

Fixture payload shaped like PR #8 @ 5bc43fe (VehicleCluster, PriceObservation,
Source, Seller, vehicle_key) and PR #3 ListingLocation latitude/longitude.
ListingLocation has no zip field. Provenance hashes are left on those drafts.
"""

from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.api.vehicle_key import observation_id, vehicle_key_for, vin_key

router = APIRouter()

NOTE = (
    "Fixture listings shaped like PR #8 @ 5bc43fe "
    "(VehicleCluster, PriceObservation, Source, Seller, vehicle_key), "
    "stacked on PR #3 ListingLocation lat/lon. "
    "ListingLocation has no zip field. "
    "Cluster result follows PR #12 @ 9cff34b: deal_score, deal_rating, estimate, "
    "confidence, and comp_count. deal_rating is great, good, fair, or high; "
    "overpriced maps to high; null only when there is no estimate."
)

_EARTH_MILES = 3958.7613
_GAZETTEER = {
    "austin": (30.2672, -97.7431, "Austin, TX"),
    "portland": (45.5152, -122.6784, "Portland, OR"),
    "denver": (39.7392, -104.9903, "Denver, CO"),
    "los angeles": (34.0522, -118.2437, "Los Angeles, CA"),
}
_SOURCES = {
    "bat": ("auction", "Bring a Trailer", "https://bringatrailer.com"),
    "ebay": ("marketplace", "eBay", "https://www.ebay.com"),
    "hemmings": ("marketplace", "Hemmings", "https://www.hemmings.com"),
    "craigslist": ("marketplace", "Craigslist", "https://www.craigslist.org"),
    "autotrader": ("dealer", "Autotrader", "https://www.autotrader.com"),
}


class ListingLocationOut(BaseModel):
    """PR #3 ListingLocation. No zip field."""

    label: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PriceObservationOut(BaseModel):
    listing_id: str
    observed_at: str
    amount: float
    currency: str = "USD"
    kind: str


class SourceOut(BaseModel):
    code: str
    kind: str
    name: str
    base_url: str
    robots_ok: bool = False
    tos_reviewed: bool = False


class SellerOut(BaseModel):
    name: Optional[str] = None
    seller_type: str


class ListingOut(BaseModel):
    observation_id: str
    vin: Optional[str] = None
    vin_note: Optional[str] = None
    year: int
    make: str
    model: str
    trim: Optional[str] = None
    mileage: Optional[int] = None
    price: float
    currency: str = "USD"
    location: ListingLocationOut
    seller_type: str
    seller: SellerOut
    source: str
    source_detail: SourceOut
    source_url: str
    title: Optional[str] = None
    vehicle_key: str
    match_method: str
    prices: list[PriceObservationOut] = Field(default_factory=list)
    distance_miles: Optional[float] = None


class EstimateOut(BaseModel):
    """PR #12 Estimate. Amounts are null when there is no estimate."""

    low: Optional[float] = None
    mid: Optional[float] = None
    high: Optional[float] = None


class ClusterResultOut(BaseModel):
    """PR #12 ClusterResult. overpriced is stored as high. null is unknown only."""

    deal_score: Optional[float] = None
    deal_rating: Optional[str] = None
    estimate: EstimateOut
    confidence: float
    comp_count: int


class ClusterOut(BaseModel):
    vehicle_key: str
    listing_ids: list[str]
    match_method: str
    result: ClusterResultOut


# Fixture estimates keyed by model. Asking is the latest asking observation.
# deal_score = (mid - asking) / mid. Positive means below market.
_ESTIMATES: dict[str, dict[str, float | int]] = {
    "M3": {"low": 36000, "mid": 40000, "high": 46000, "confidence": 0.8, "comp_count": 4},
    "RX-7": {"low": 31000, "mid": 34800, "high": 39000, "confidence": 0.45, "comp_count": 2},
    "S2000": {"low": 22000, "mid": 24000, "high": 25500, "confidence": 0.35, "comp_count": 1},
}


def _deal_rating(score: float) -> str:
    """rate_deal bands. A score below -0.15 is overpriced upstream and maps to high."""
    if score >= 0.15:
        return "great"
    if score >= 0.05:
        return "good"
    if score >= -0.05:
        return "fair"
    return "high"


def _pricing(model: str, asking: float) -> ClusterResultOut:
    spec = _ESTIMATES.get(model)
    if spec is None or float(spec["mid"]) <= 0:
        return ClusterResultOut(
            deal_score=None,
            deal_rating=None,
            estimate=EstimateOut(),
            confidence=0.0,
            comp_count=0,
        )
    mid = float(spec["mid"])
    score = round((mid - asking) / mid, 4)
    return ClusterResultOut(
        deal_score=score,
        deal_rating=_deal_rating(score),
        estimate=EstimateOut(low=float(spec["low"]), mid=mid, high=float(spec["high"])),
        confidence=float(spec["confidence"]),
        comp_count=int(spec["comp_count"]),
    )


class ListingSearchResponse(BaseModel):
    listings: list[ListingOut]
    clusters: list[ClusterOut]
    total: int
    note: str


def _source(code: str) -> SourceOut:
    kind, name, base_url = _SOURCES[code]
    return SourceOut(code=code, kind=kind, name=name, base_url=base_url)


def _listing(raw: dict) -> ListingOut:
    location = ListingLocationOut(**raw["location"])
    raw_vin = raw.get("vin")
    normalized = vin_key(raw_vin)
    key = vehicle_key_for(
        vin=raw_vin,
        year=raw["year"],
        make=raw["make"],
        model=raw["model"],
        trim=raw.get("trim"),
        mileage=raw.get("mileage"),
        label=location.label,
    )
    obs = observation_id(raw["source"], raw["source_url"])
    prices = [
        PriceObservationOut(listing_id=obs, **price) for price in raw.get("prices", [])
    ]
    return ListingOut(
        observation_id=obs,
        vin=normalized,
        vin_note=raw.get("vin_note"),
        year=raw["year"],
        make=raw["make"],
        model=raw["model"],
        trim=raw.get("trim"),
        mileage=raw.get("mileage"),
        price=raw["price"],
        currency=raw.get("currency", "USD"),
        location=location,
        seller_type=raw["seller_type"],
        seller=SellerOut(seller_type=raw["seller_type"]),
        source=raw["source"],
        source_detail=_source(raw["source"]),
        source_url=raw["source_url"],
        title=raw.get("title"),
        vehicle_key=key,
        match_method="vin" if normalized and normalized == key else "fuzzy",
        prices=prices,
    )


def fixture_listings() -> list[ListingOut]:
    """Same cars as shared/fixtures/listings on PR #8 @ 5bc43fe."""
    return [
        _listing(
            {
                "vin": "1HGCM82633A004352",
                "year": 2003,
                "make": "BMW",
                "model": "M3",
                "trim": "Coupe",
                "mileage": 62140,
                "price": 31200,
                "location": {
                    "label": "Austin, TX 78701",
                    "city": "Austin",
                    "region": "TX",
                    "country": "US",
                    "latitude": 30.2672,
                    "longitude": -97.7431,
                },
                "seller_type": "auction",
                "source": "bat",
                "source_url": "https://bringatrailer.com/listing/deaven-demo-2003-bmw-m3",
                "title": "2003 BMW M3 Coupe",
                "prices": [
                    {"observed_at": "2026-07-01T00:00:00Z", "amount": 34800, "kind": "asking"},
                    {"observed_at": "2026-07-15T18:30:00Z", "amount": 30500, "kind": "bid"},
                    {"observed_at": "2026-08-01T00:00:00Z", "amount": 31200, "kind": "asking"},
                ],
            }
        ),
        _listing(
            {
                "vin": "1hg-cm82633-a004352",
                "year": 2003,
                "make": "BMW",
                "model": "M3",
                "trim": "Coupe",
                "mileage": 62210,
                "price": 32950,
                "location": {
                    "label": "Austin, TX 78701",
                    "city": "Austin",
                    "region": "TX",
                    "country": "US",
                    "latitude": 30.2672,
                    "longitude": -97.7431,
                },
                "seller_type": "marketplace",
                "source": "ebay",
                "source_url": "https://www.ebay.com/itm/deaven-demo-2003-bmw-m3",
                "title": "2003 BMW M3 Coupe",
                "prices": [
                    {"observed_at": "2026-07-18T00:00:00Z", "amount": 33900, "kind": "asking"},
                    {"observed_at": "2026-07-20T00:00:00Z", "amount": 32950, "kind": "asking"},
                ],
            }
        ),
        _listing(
            {
                "vin": None,
                "vin_note": "missing",
                "year": 1993,
                "make": "Mazda",
                "model": "RX-7",
                "trim": "Touring",
                "mileage": 78400,
                "price": 32500,
                "location": {
                    "label": "Portland, OR 97202",
                    "city": "Portland",
                    "region": "OR",
                    "country": "US",
                },
                "seller_type": "marketplace",
                "source": "hemmings",
                "source_url": "https://www.hemmings.com/listing/deaven-demo-1993-mazda-rx7",
                "title": "1993 Mazda RX-7 Touring",
            }
        ),
        _listing(
            {
                "vin": "JH4KA8260MC000000",
                "vin_note": "invalid",
                "year": 1991,
                "make": "Acura",
                "model": "Legend",
                "trim": "L",
                "mileage": 142000,
                "price": 18000,
                "location": {
                    "label": "Denver, CO 80202",
                    "city": "Denver",
                    "region": "CO",
                    "country": "US",
                },
                "seller_type": "marketplace",
                "source": "craigslist",
                "source_url": "https://example.com/listings/invalid-vin",
                "title": "1991 Acura Legend L",
            }
        ),
        _listing(
            {
                "vin": None,
                "vin_note": "missing",
                "year": 2006,
                "make": "Honda",
                "model": "S2000",
                "trim": "Base",
                "mileage": 41000,
                "price": 27500,
                "location": {
                    "label": "Los Angeles, CA 90012",
                    "city": "Los Angeles",
                    "region": "CA",
                    "country": "US",
                },
                "seller_type": "dealer",
                "source": "autotrader",
                "source_url": "https://www.autotrader.com/cars-for-sale/deaven-demo-2006-honda-s2000",
                "title": "2006 Honda S2000",
            }
        ),
    ]


def _distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    def rad(degrees: float) -> float:
        return degrees * math.pi / 180

    d_lat = rad(lat2 - lat1)
    d_lon = rad(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * _EARTH_MILES * math.asin(min(1.0, math.sqrt(a)))


def _resolve(location: str) -> Optional[tuple[float, float]]:
    text = location.strip()
    if not text:
        return None
    if "," in text:
        left, right = text.split(",", 1)
        try:
            lat = float(left.strip())
            lon = float(right.strip())
        except ValueError:
            lat = lon = None
        else:
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
    city = text.split(",")[0].strip().casefold()
    found = _GAZETTEER.get(city)
    if found is None:
        return None
    return found[0], found[1]


def _cluster_asking(items: list[ListingOut]) -> float:
    """Latest asking observation, otherwise the listing price."""
    points = [
        (price.observed_at, price.amount)
        for item in items
        for price in item.prices
        if price.kind == "asking"
    ]
    if points:
        points.sort()
        return points[-1][1]
    return min(item.price for item in items)


def _clusters(listings: list[ListingOut]) -> list[ClusterOut]:
    order: list[str] = []
    buckets: dict[str, list[ListingOut]] = {}
    for item in listings:
        if item.vehicle_key not in buckets:
            order.append(item.vehicle_key)
            buckets[item.vehicle_key] = []
        buckets[item.vehicle_key].append(item)
    return [
        ClusterOut(
            vehicle_key=key,
            listing_ids=[item.observation_id for item in buckets[key]],
            match_method=buckets[key][0].match_method,
            result=_pricing(buckets[key][0].model, _cluster_asking(buckets[key])),
        )
        for key in order
    ]


def search_listings(
    *,
    make: Optional[str] = None,
    model: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    mileage_max: Optional[int] = None,
    location: Optional[str] = None,
    radius: Optional[float] = None,
) -> ListingSearchResponse:
    center = _resolve(location) if location and location.strip() else None
    if location and location.strip() and center is None:
        return ListingSearchResponse(listings=[], clusters=[], total=0, note=NOTE)
    radius_miles = 100.0 if radius is None else radius
    matched: list[ListingOut] = []
    for item in fixture_listings():
        if make and make.strip().casefold() not in item.make.casefold():
            continue
        if model and model.strip().casefold() not in item.model.casefold():
            continue
        if year_min is not None and item.year < year_min:
            continue
        if year_max is not None and item.year > year_max:
            continue
        if price_min is not None and item.price < price_min:
            continue
        if price_max is not None and item.price > price_max:
            continue
        if mileage_max is not None and item.mileage is not None and item.mileage > mileage_max:
            continue
        if center is not None:
            if item.location.latitude is None or item.location.longitude is None:
                continue
            distance = _distance(
                center[0], center[1], item.location.latitude, item.location.longitude
            )
            if distance > radius_miles:
                continue
            item = item.model_copy(update={"distance_miles": distance})
        matched.append(item)
    return ListingSearchResponse(
        listings=matched,
        clusters=_clusters(matched),
        total=len(matched),
        note=NOTE,
    )


@router.get("/api/listings/search", response_model=ListingSearchResponse)
async def listings_search(
    make: Optional[str] = None,
    model: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    mileage_max: Optional[int] = None,
    location: Optional[str] = None,
    radius: Optional[float] = Query(default=None, ge=0, le=5000),
):
    return search_listings(
        make=make,
        model=model,
        year_min=year_min,
        year_max=year_max,
        price_min=price_min,
        price_max=price_max,
        mileage_max=mileage_max,
        location=location,
        radius=radius,
    )
