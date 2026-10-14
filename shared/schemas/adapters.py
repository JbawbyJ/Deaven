"""Map DealPayload to NormalizedListing and back.

DealPayload stays the scoring record. NormalizedListing is the ingestion
record from PR #3. Fields that exist only on one side are not invented.
"""

from __future__ import annotations

from datetime import datetime, timezone

from shared.schemas.deal import DealPayload, DealSource, ListingData
from shared.schemas.listing import ListingLocation, NormalizedListing, build_provenance, url_photo
from shared.schemas.market import source_for
from shared.vin import vin_key


def listing_from_deal(deal: DealPayload) -> NormalizedListing:
    """Build a normalized listing. An invalid VIN is kept in provenance and stored as null."""
    data = deal.listing
    if data.year is None or not (data.make and data.make.strip()) or not (data.model and data.model.strip()):
        raise ValueError("deal listing needs year, make, and model")

    source_code = deal.source if isinstance(deal.source, str) else deal.source.value
    channel = source_for(source_code)
    seen = _as_utc(deal.ingested_at)
    first = _as_utc(data.listing_date) if data.listing_date else seen
    last = _as_utc(data.end_date) if data.end_date else first
    if last < first:
        last = first

    raw_vin = data.vin if isinstance(data.vin, str) else None
    normalized_vin = vin_key(raw_vin) if raw_vin and raw_vin.strip() else None
    payload = {
        "title": data.title,
        "price": data.price,
        "mileage": data.mileage,
        "year": data.year,
        "make": data.make,
        "model": data.model,
        "trim": data.trim,
        "vin": raw_vin,
        "location": data.location,
        "seller_type": data.seller_type,
        "transmission": data.transmission,
        "drivetrain": data.drivetrain,
        "color_ext": data.color_ext,
        "color_int": data.color_int,
    }
    photos = [
        url_photo(url)
        for url in deal.images
        if url.strip().startswith(("http://", "https://"))
    ]
    return NormalizedListing(
        vin=normalized_vin,
        year=data.year,
        make=data.make.strip(),
        model=data.model.strip(),
        trim=data.trim,
        mileage=data.mileage,
        price=data.price,
        currency="USD",
        location=_location_from_label(data.location),
        seller_type=channel.kind,
        source=source_code,
        source_url=deal.url,
        title=data.title,
        photos=photos,
        first_seen=first,
        last_seen=last,
        provenance=build_provenance(
            source=source_code,
            source_url=deal.url,
            fetched_at=seen,
            payload=payload,
        ),
    )


def deal_from_listing(listing: NormalizedListing) -> DealPayload:
    """Score-pipeline record for a normalized listing. Price is the listing's asking price."""
    try:
        source = DealSource(listing.source)
    except ValueError:
        source = DealSource.MANUAL
    title = listing.title or " ".join(
        part
        for part in (str(listing.year), listing.make, listing.model, listing.trim or "")
        if part
    )
    return DealPayload(
        source=source,
        url=listing.source_url,
        ingested_at=listing.first_seen,
        images=[photo.url for photo in listing.photos],
        listing=ListingData(
            title=title.strip(),
            price=listing.price,
            mileage=listing.mileage,
            year=listing.year,
            make=listing.make,
            model=listing.model,
            trim=listing.trim,
            vin=listing.vin,
            location=_label(listing.location),
        ),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _location_from_label(raw: str | None) -> ListingLocation:
    if not raw or not raw.strip():
        return ListingLocation()
    label = raw.strip()
    if "," not in label:
        return ListingLocation(label=label, city=label)
    city, rest = [part.strip() for part in label.split(",", 1)]
    tokens = rest.split()
    region = tokens[0] if tokens else None
    return ListingLocation(label=label, city=city or None, region=region)


def _label(location: ListingLocation) -> str | None:
    if location.label:
        return location.label
    if location.city and location.region:
        return f"{location.city}, {location.region}"
    return location.city or location.region
