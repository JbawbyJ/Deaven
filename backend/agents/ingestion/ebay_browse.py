"""Official eBay Browse API adapter. This is the live eBay path.

HTML parsing stays in ebay.py for saved fixtures. This module does not scrape
ebay.com. Credentials come from EBAY_CLIENT_ID and EBAY_CLIENT_SECRET.
Tests pass a transport; nothing here opens a socket unless that transport does.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from shared.schemas.deal import DealSource
from shared.schemas.listing import ListingLocation, NormalizedListing, build_provenance, url_photo
from shared.schemas.market import PriceKind, PriceObservation, source_for
from shared.vin import vin_key

from backend.agents.ingestion.extract import ParsedPage, miles_from_text, parse_title
from backend.agents.ingestion.policy import USER_AGENT, LiveFetchBlocked, SourcePolicy

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/{item_id}"
OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"
MARKETPLACE_ID = "EBAY_MOTORS"
TOS_URL = "https://www.ebay.com.au/help/policies/member-behaviour-policies/user-agreement?id=4259"

TOS_NOTE = (
    "Live eBay access uses the Browse API, not HTML scraping. "
    "User Agreement section 15 bars robots and scrapers without express written permission: "
    f"{TOS_URL}. "
    "Application credentials are read from EBAY_CLIENT_ID and EBAY_CLIENT_SECRET. "
    "No credential value is stored in the repo."
)

POLICY = SourcePolicy(
    code=DealSource.EBAY,
    user_agent=USER_AGENT,
    min_interval_seconds=3.0,
    tos_note=TOS_NOTE,
    tos_url=TOS_URL,
    live_fetch_allowed=True,
    review_status="official Browse API",
)
LIVE_FETCH_ALLOWED = POLICY.live_fetch_allowed

Transport = Callable[..., dict[str, Any]]


class MissingEbayCredentials(RuntimeError):
    """EBAY_CLIENT_ID or EBAY_CLIENT_SECRET is unset. No request was sent."""


def credentials_from_env() -> tuple[str, str]:
    client_id = os.environ.get("EBAY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("EBAY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise MissingEbayCredentials("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required")
    return client_id, client_secret


def token_request(client_id: str, client_secret: str) -> dict[str, Any]:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
    return {
        "method": "POST",
        "url": TOKEN_URL,
        "headers": {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        "body": urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": OAUTH_SCOPE}
        ),
        "params": None,
    }


def search_request(access_token: str, query: str) -> dict[str, Any]:
    return {
        "method": "GET",
        "url": SEARCH_URL,
        "headers": {
            "Authorization": f"Bearer {access_token}",
            "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE_ID,
        },
        "body": None,
        "params": {"q": query, "limit": "50", "category_ids": "6001"},
    }


def urllib_transport(method: str, url: str, *, headers: dict[str, str], body: str | None = None, params: dict[str, str] | None = None) -> dict[str, Any]:
    """Live HTTP call. Tests must not use this; pass a fake transport instead."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = body.encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def fetch_search(query: str, *, fetched_at: datetime, transport: Transport | None = None) -> ParsedPage:
    """Search Browse item summaries. Credentials are checked before any request."""
    if not POLICY.live_fetch_allowed:
        raise LiveFetchBlocked(POLICY.code.value)
    client_id, client_secret = credentials_from_env()
    send = transport or urllib_transport
    token_call = token_request(client_id, client_secret)
    token_payload = send(
        token_call["method"],
        token_call["url"],
        headers=token_call["headers"],
        body=token_call["body"],
        params=token_call["params"],
    )
    access_token = str(token_payload.get("access_token") or "")
    if not access_token:
        raise ValueError("Browse token response did not include access_token")
    search_call = search_request(access_token, query)
    payload = send(
        search_call["method"],
        search_call["url"],
        headers=search_call["headers"],
        body=search_call["body"],
        params=search_call["params"],
    )
    return parse_browse_payload(payload, fetched_at=fetched_at)


def parse_browse_payload(payload: dict[str, Any], *, fetched_at: datetime) -> ParsedPage:
    """Map a Browse search body or a single item into NormalizedListing rows."""
    if "itemSummaries" in payload:
        items = list(payload.get("itemSummaries") or [])
    else:
        items = [payload]
    page = ParsedPage()
    for item in items:
        built = _item_to_listing(item, fetched_at=fetched_at)
        if built is None:
            continue
        listing, prices = built
        page.listings.append(listing)
        page.prices.extend(prices)
    return page


def _item_to_listing(
    item: dict[str, Any], *, fetched_at: datetime
) -> tuple[NormalizedListing, list[PriceObservation]] | None:
    title = str(item.get("title") or "").strip()
    named = parse_title(title)
    price = item.get("price") or {}
    raw_amount = price.get("value")
    source_url = str(item.get("itemWebUrl") or "").strip()
    if named is None or raw_amount in (None, "") or not source_url:
        return None
    amount = float(str(raw_amount).replace(",", ""))
    currency = str(price.get("currency") or "USD")
    year, make, model, title_trim = named
    aspects = _aspects(item)
    trim = aspects.get("trim") or title_trim
    raw_vin = aspects.get("vin")
    normalized_vin = vin_key(raw_vin) if raw_vin else None
    mileage, mileage_payload = miles_from_text(aspects.get("mileage"), default_unit="mi")
    first_seen = _when(item.get("itemCreationDate"), fetched_at)
    last_seen = _when(item.get("itemEndDate"), fetched_at)
    if last_seen < first_seen:
        last_seen = first_seen
    image = _image_url(item)
    channel = source_for(DealSource.EBAY)
    listing = NormalizedListing(
        vin=normalized_vin,
        year=year,
        make=make,
        model=model,
        trim=trim,
        mileage=mileage,
        price=amount,
        currency=currency,
        location=_location(item),
        seller_type=channel.kind,
        source=DealSource.EBAY.value,
        source_url=source_url,
        title=title,
        photos=[url_photo(image)] if image else [],
        first_seen=first_seen,
        last_seen=last_seen,
        provenance=build_provenance(
            source=DealSource.EBAY.value,
            source_url=source_url,
            fetched_at=_aware(fetched_at),
            payload={
                "itemId": item.get("itemId"),
                "title": title,
                "price": price,
                "vin": raw_vin,
                **mileage_payload,
            },
        ),
    )
    prices = [
        PriceObservation(
            listing_id=listing.observation_id,
            observed_at=listing.provenance.fetched_at,
            amount=listing.price,
            currency=listing.currency,
            kind=PriceKind.ASKING,
        )
    ]
    return listing, prices


def _aspects(item: dict[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    for aspect in item.get("localizedAspects") or []:
        name = str(aspect.get("name") or "").strip().casefold()
        value = aspect.get("value")
        if name and value not in (None, ""):
            found[name] = str(value).strip()
    return found


def _location(item: dict[str, Any]) -> ListingLocation:
    raw = item.get("itemLocation") or {}
    city = _text(raw.get("city"))
    region = _text(raw.get("stateOrProvince"))
    postal = _text(raw.get("postalCode"))
    country = _text(raw.get("country")) or "US"
    if len(country) != 2:
        country = "US"
    if city and region and postal:
        label = f"{city}, {region} {postal}"
    elif city and region:
        label = f"{city}, {region}"
    else:
        label = city or region
    return ListingLocation(label=label, city=city, region=region, country=country)


def _image_url(item: dict[str, Any]) -> str | None:
    image = item.get("image") or {}
    url = _text(image.get("imageUrl"))
    if url and url.startswith(("http://", "https://")):
        return url
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _when(value: Any, fallback: datetime) -> datetime:
    if not value:
        return _aware(fallback)
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return _aware(parsed)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("fetched_at must be timezone-aware")
    return value.astimezone(timezone.utc)
