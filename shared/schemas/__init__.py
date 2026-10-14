"""Shared Pydantic schemas."""

from shared.schemas.adapters import deal_from_listing, listing_from_deal
from shared.schemas.listing import (
    CanonicalListing,
    ListingLocation,
    ListingPhoto,
    MatchMethod,
    NormalizedListing,
    PhotoHashKind,
    RawProvenance,
    SellerType,
)
from shared.schemas.market import (
    PriceKind,
    PriceObservation,
    Seller,
    Source,
    VehicleCluster,
    source_for,
    vehicle_key,
)

__all__ = [
    "CanonicalListing",
    "ListingLocation",
    "ListingPhoto",
    "MatchMethod",
    "NormalizedListing",
    "PhotoHashKind",
    "PriceKind",
    "PriceObservation",
    "RawProvenance",
    "Seller",
    "SellerType",
    "Source",
    "VehicleCluster",
    "deal_from_listing",
    "listing_from_deal",
    "source_for",
    "vehicle_key",
]
