"""Shared HTML field reading for the four source adapters.

Identity, money, and location are parsed here. VIN checks go through
shared.vin.vin_key. Seller channel comes from source_for. The fuzzy
vehicle key is not computed in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin

from shared.schemas.deal import DealSource
from shared.schemas.listing import (
    ListingLocation,
    NormalizedListing,
    build_provenance,
    url_photo,
)
from shared.schemas.market import PriceKind, PriceObservation, source_for
from shared.vin import vin_key

from backend.agents.ingestion.htmltree import (
    Node,
    by_class,
    first_class,
    paired_fields,
    parse_document,
    text_of,
    walk,
)

# Same factor the TCV scraper uses when it stores miles. The raw kilometer
# figure stays in provenance; vehicle_key's band is a mile band.
KM_TO_MILES = 0.621371

_MONEY = re.compile(
    r"(?P<cur>US\s*\$|USD|JPY|¥|￥|\$|£|€)\s*(?P<amt>[\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_MILEAGE = re.compile(r"([\d,]+)\s*(mi|miles|km|kilometers)?", re.IGNORECASE)
_TITLE = re.compile(r"^(19\d{2}|20\d{2})\s+(.+)$")
_MULTI_WORD_MAKES = (
    "alfa romeo",
    "aston martin",
    "land rover",
    "mercedes-benz",
    "mercedes benz",
    "rolls-royce",
    "rolls royce",
)
_COUNTRY = {
    "us": "US",
    "usa": "US",
    "united states": "US",
    "japan": "JP",
    "jp": "JP",
    "canada": "CA",
    "uk": "GB",
    "united kingdom": "GB",
}


@dataclass
class ParsedPage:
    listings: list[NormalizedListing] = field(default_factory=list)
    prices: list[PriceObservation] = field(default_factory=list)


def parse_cards(
    html: str,
    *,
    fetched_at: datetime,
    code: DealSource,
    card_class: str,
    title_class: str,
    price_class: str,
    base_url: str,
    default_country: str,
    location_class: str | None = None,
    map_class: str | None = None,
    mileage_unit: str = "mi",
) -> ParsedPage:
    fetched_at = _aware(fetched_at, "fetched_at")
    root = parse_document(html)
    page = ParsedPage()
    canonical = _canonical(root, base_url)
    for card in by_class(root, card_class):
        built = _card_to_listing(
            card,
            fetched_at=fetched_at,
            code=code,
            title_class=title_class,
            price_class=price_class,
            base_url=base_url,
            default_country=default_country,
            location_class=location_class,
            map_class=map_class,
            mileage_unit=mileage_unit,
            canonical=canonical,
        )
        if built is None:
            continue
        listing, prices = built
        page.listings.append(listing)
        page.prices.extend(prices)
    return page


def _card_to_listing(
    card: Node,
    *,
    fetched_at: datetime,
    code: DealSource,
    title_class: str,
    price_class: str,
    base_url: str,
    default_country: str,
    location_class: str | None,
    map_class: str | None,
    mileage_unit: str,
    canonical: str | None,
) -> tuple[NormalizedListing, list[PriceObservation]] | None:
    title = text_of(first_class(card, title_class))
    named = parse_title(title or "")
    price_text = text_of(first_class(card, price_class))
    money = parse_money(price_text or "")
    source_url = _card_url(card, base_url) or canonical
    if named is None or money is None or not source_url:
        return None

    year, make, model, title_trim = named
    fields = paired_fields(card)
    trim = fields.get("trim") or title_trim
    raw_vin = _clean_vin(fields.get("vin") or fields.get("chassis"))
    normalized_vin = vin_key(raw_vin) if raw_vin else None
    mileage, mileage_payload = miles_from_text(fields.get("mileage"), default_unit=mileage_unit)
    location_text = fields.get("location") or text_of(first_class(card, location_class or ""))
    latitude, longitude = _coordinates(card, map_class)
    location = location_from_text(
        location_text,
        default_country=default_country,
        latitude=latitude,
        longitude=longitude,
    )
    amount, currency = money
    first_seen = _time_in(card, "first-seen") or fetched_at
    last_seen = _time_in(card, "last-seen") or fetched_at
    if last_seen < first_seen:
        last_seen = first_seen
    image = _image_url(card)
    payload: dict = {
        "title": title,
        "price_text": price_text,
        "vin": raw_vin,
        "mileage_text": fields.get("mileage"),
        "location_text": location_text,
        "trim": trim,
        **mileage_payload,
    }
    channel = source_for(code)
    listing = NormalizedListing(
        vin=normalized_vin,
        year=year,
        make=make,
        model=model,
        trim=trim,
        mileage=mileage,
        price=amount,
        currency=currency,
        location=location,
        seller_type=channel.kind,
        source=code.value,
        source_url=source_url,
        title=title,
        photos=[url_photo(image)] if image else [],
        first_seen=first_seen,
        last_seen=last_seen,
        provenance=build_provenance(
            source=code.value,
            source_url=source_url,
            fetched_at=fetched_at,
            payload=payload,
        ),
    )
    prices = _price_history(card, listing.observation_id)
    if not prices:
        prices = [
            PriceObservation(
                listing_id=listing.observation_id,
                observed_at=fetched_at,
                amount=listing.price,
                currency=listing.currency,
                kind=PriceKind.ASKING,
            )
        ]
    return listing, prices


def parse_title(title: str) -> tuple[int, str, str, str | None] | None:
    match = _TITLE.match(title.strip())
    if not match:
        return None
    year = int(match.group(1))
    rest = match.group(2).strip()
    lower = rest.casefold()
    make: str | None = None
    for multi in _MULTI_WORD_MAKES:
        if lower.startswith(multi + " "):
            make = rest[: len(multi)]
            rest = rest[len(multi) :].strip()
            break
    if make is None:
        bits = rest.split()
        if len(bits) < 2:
            return None
        make = bits[0]
        rest = " ".join(bits[1:])
    model_bits = rest.split()
    if not model_bits:
        return None
    trim = " ".join(model_bits[1:]) or None
    return year, make, model_bits[0], trim


def parse_money(text: str) -> tuple[float, str] | None:
    match = _MONEY.search(text.replace("\xa0", " "))
    if not match:
        return None
    amount = float(match.group("amt").replace(",", ""))
    token = match.group("cur").upper()
    if "JPY" in token or "¥" in token or "￥" in token:
        currency = "JPY"
    elif "£" in token:
        currency = "GBP"
    elif "€" in token:
        currency = "EUR"
    else:
        currency = "USD"
    return amount, currency


def miles_from_text(text: str | None, *, default_unit: str = "mi") -> tuple[int | None, dict]:
    if not text or not text.strip():
        return None, {}
    match = _MILEAGE.search(text)
    payload = {"mileage_text": " ".join(text.split())}
    if not match:
        return None, payload
    number = int(match.group(1).replace(",", ""))
    unit = (match.group(2) or default_unit).casefold()
    if unit.startswith("km") or unit.startswith("kilometer"):
        payload["mileage_km"] = number
        payload["mileage_unit"] = "km"
        return int(round(number * KM_TO_MILES)), payload
    payload["mileage_unit"] = "mi"
    return number, payload


def location_from_text(
    text: str | None,
    *,
    default_country: str | None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> ListingLocation:
    if latitude is None or longitude is None:
        latitude = None
        longitude = None
    if not text or not text.strip():
        return ListingLocation(country=default_country, latitude=latitude, longitude=longitude)
    label = " ".join(text.split())
    label = re.sub(r"^(located in|location)\s*:\s*", "", label, flags=re.IGNORECASE)
    parts = [part.strip() for part in label.split(",") if part.strip()]
    country = default_country
    if parts and parts[-1].casefold() in _COUNTRY:
        country = _COUNTRY[parts[-1].casefold()]
        parts = parts[:-1]
    city = parts[0] if parts else None
    region = parts[1].split()[0] if len(parts) > 1 else None
    return ListingLocation(
        label=label,
        city=city,
        region=region,
        country=country,
        latitude=latitude,
        longitude=longitude,
    )


def _price_history(card: Node, listing_id: str) -> list[PriceObservation]:
    rows: list[PriceObservation] = []
    seen: set[int] = set()
    for class_name in ("price-history", "bid-history"):
        for table in by_class(card, class_name):
            for node in walk(table):
                if node.tag != "tr" or id(node) in seen:
                    continue
                seen.add(id(node))
                parsed = _history_row(node, listing_id)
                if parsed is not None:
                    rows.append(parsed)
    return rows


def _row_cells(row: Node) -> dict[str, Node] | None:
    if row.tag != "tr":
        return None
    cells: dict[str, Node] = {}
    for child in row.children:
        if child.tag not in {"td", "th"}:
            continue
        for class_name in child.classes:
            cells[class_name] = child
    return cells


def _history_row(row: Node, listing_id: str) -> PriceObservation | None:
    cells = _row_cells(row)
    if not cells:
        return None
    when = cells.get("when")
    kind = cells.get("kind")
    amount = cells.get("amount")
    if when is None or kind is None or amount is None:
        return None
    money = parse_money(amount.text())
    observed = _parse_time(when.text())
    if money is None or observed is None:
        return None
    try:
        price_kind = PriceKind(kind.text().strip().casefold())
    except ValueError:
        return None
    value, currency = money
    return PriceObservation(
        listing_id=listing_id,
        observed_at=observed,
        amount=value,
        currency=currency,
        kind=price_kind,
    )


def _coordinates(card: Node, map_class: str | None) -> tuple[float | None, float | None]:
    if not map_class:
        return None, None
    node = first_class(card, map_class)
    if node is None:
        return None, None
    raw_lat = node.attrs.get("data-latitude")
    raw_lon = node.attrs.get("data-longitude")
    if not raw_lat or not raw_lon:
        return None, None
    try:
        return float(raw_lat), float(raw_lon)
    except ValueError:
        return None, None


def _image_url(card: Node) -> str | None:
    for node in walk(card):
        if node.tag != "img":
            continue
        src = node.attrs.get("src", "").strip()
        if src.startswith(("http://", "https://")):
            return src
    return None


def _card_url(card: Node, base_url: str) -> str | None:
    for node in walk(card):
        if node.tag != "a":
            continue
        href = node.attrs.get("href", "").strip()
        if href and not href.startswith(("#", "javascript:")):
            return urljoin(base_url, href)
    data_url = card.attrs.get("data-url", "").strip()
    if data_url:
        return urljoin(base_url, data_url)
    return None


def _canonical(root: Node, base_url: str) -> str | None:
    for node in walk(root):
        if node.tag != "link":
            continue
        rel = set(node.attrs.get("rel", "").casefold().split())
        href = node.attrs.get("href", "").strip()
        if "canonical" in rel and href:
            return urljoin(base_url, href)
    return None


def _time_in(card: Node, class_name: str) -> datetime | None:
    node = first_class(card, class_name)
    if node is None:
        return None
    return _parse_time(node.attrs.get("datetime") or node.text())


def _parse_time(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _aware(parsed, "timestamp")


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _clean_vin(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"^\s*vin\s*:?\s*", "", text.strip(), flags=re.IGNORECASE)
    return cleaned or None
