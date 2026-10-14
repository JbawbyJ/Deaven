"""
eBay Motors listings via the official Finding API.

This is the one live adapter. It does not scrape HTML. `EBAY_APP_ID` comes
from the environment. Tests pass a transport and fixture bodies.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

from backend.agents.scrapers.ebay import extract_year_make_model
from backend.ingestion.http import (
    USER_AGENT,
    DomainRateLimiter,
    RobotsDisallowed,
    Transport,
    decide_robots,
    default_transport,
    host_of,
    robots_url_for,
)
from shared.schemas.deal import ListingData
from shared.vin import is_valid_vin

FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
_MILEAGE_RE = re.compile(r"([\d,]+)\s*(?:mi|miles)\b", re.IGNORECASE)


class MissingAppId(Exception):
    """EBAY_APP_ID is required before any request."""


class EbayFindingError(Exception):
    """The Finding API response could not be used."""


class EbayFindingAdapter:
    def __init__(
        self,
        app_id: Optional[str] = None,
        transport: Optional[Transport] = None,
        min_interval_s: float = 1.0,
        clock=None,
        sleep=None,
        user_agent: str = USER_AGENT,
    ) -> None:
        if app_id is None:
            app_id = os.getenv("EBAY_APP_ID", "")
        self.app_id = app_id.strip()
        self._transport = transport or default_transport
        self._user_agent = user_agent
        self._limiter = DomainRateLimiter(min_interval_s, clock=clock, sleep=sleep)
        self._robots_body: dict[str, str] = {}

    def fetch(
        self,
        keywords: str,
        *,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
    ) -> list[ListingData]:
        query = keywords.strip()
        if not query:
            raise ValueError("keywords are required")
        if not self.app_id:
            raise MissingAppId("Set EBAY_APP_ID to call the eBay Finding API")

        api_url = _finding_url(self.app_id, query, price_min, price_max)
        host = host_of(api_url)
        decision = self._load_robots(host, api_url)
        if not decision.allowed:
            raise RobotsDisallowed(api_url, decision.reason)
        self._limiter.acquire(host, crawl_delay_s=decision.crawl_delay_s)
        status, body = self._get(api_url)
        if status != 200:
            raise EbayFindingError(f"Finding API HTTP {status}")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise EbayFindingError("Finding API returned invalid JSON") from exc
        return parse_finding_response(payload)

    def _load_robots(self, host: str, api_url: str):
        body = self._robots_body.get(host)
        if body is None:
            self._limiter.acquire(host)
            status, body = self._get(robots_url_for(api_url))
            if status != 200:
                raise RobotsDisallowed(robots_url_for(api_url), "robots_unavailable")
            self._robots_body[host] = body
        return decide_robots(body, self._user_agent, api_url)

    def _get(self, url: str) -> tuple[int, str]:
        return self._transport(url, {"User-Agent": self._user_agent})


def parse_finding_response(payload: dict[str, Any]) -> list[ListingData]:
    try:
        response = payload["findItemsAdvancedResponse"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise EbayFindingError("Finding API response is missing findItemsAdvancedResponse") from exc
    ack = _first(response.get("ack"))
    if ack not in ("Success", "Warning"):
        raise EbayFindingError(f"Finding API ack={ack}")
    search_result = _first(response.get("searchResult")) or {}
    items = search_result.get("item") if isinstance(search_result, dict) else None
    if not items:
        return []
    if isinstance(items, dict):
        items = [items]
    listings: list[ListingData] = []
    for item in items:
        listing = _listing_from_item(item)
        if listing is not None:
            listings.append(listing)
    return listings


def _listing_from_item(item: dict[str, Any]) -> Optional[ListingData]:
    item_id = str(_first(item.get("itemId")) or "").strip()
    title = str(_first(item.get("title")) or "").strip()
    url = str(_first(item.get("viewItemURL")) or "").strip()
    price, currency = _price(item)
    if not item_id or not title or not url or price is None or price <= 0:
        return None

    year, make, model = extract_year_make_model(title)
    location = _text(item.get("location"))
    postal = _text(item.get("postalCode"))
    lat, lng = _coordinates(item)
    vin = _text(item.get("vin"))
    if vin and not is_valid_vin(vin):
        vin = None
    listing_info = _first(item.get("listingInfo")) or {}
    if not isinstance(listing_info, dict):
        listing_info = {}
    selling = _first(item.get("sellingStatus")) or {}
    state = _text(selling.get("sellingState")) if isinstance(selling, dict) else None
    end_time = _time(_text(listing_info.get("endTime")))
    sold = state == "EndedWithSales"

    # viewItemURL was required above. ListingData stores source + source_id,
    # not the URL (that stays on DealPayload when a deal is built).
    fields: dict[str, Any] = {
        "title": title,
        "price": price,
        "currency": currency,
        "year": year,
        "make": make,
        "model": model,
        "trim": _trim(title, year, make, model),
        "mileage": _mileage(title),
        "vin": vin,
        "location": location,
        "region": _region(location),
        "zip": postal,
        "listing_date": _time(_text(listing_info.get("startTime"))),
        "source": "ebay",
        "source_id": item_id,
    }
    if lat is not None and lng is not None:
        fields["lat"] = lat
        fields["lng"] = lng
    if sold:
        fields["sold_price"] = price
        fields["sold_at"] = end_time
    return ListingData(**fields)


def _finding_url(
    app_id: str,
    keywords: str,
    price_min: Optional[float],
    price_max: Optional[float],
) -> str:
    params: dict[str, str] = {
        "OPERATION-NAME": "findItemsAdvanced",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "true",
        "GLOBAL-ID": "EBAY-MOTOR",
        "categoryId": "6001",
        "keywords": keywords,
        "paginationInput.entriesPerPage": "20",
        "paginationInput.pageNumber": "1",
        "sortOrder": "StartTimeNewest",
        "itemFilter(0).name": "Condition",
        "itemFilter(0).value": "Used",
    }
    index = 1
    if price_min is not None:
        params[f"itemFilter({index}).name"] = "MinPrice"
        params[f"itemFilter({index}).value"] = str(price_min)
        index += 1
    if price_max is not None:
        params[f"itemFilter({index}).name"] = "MaxPrice"
        params[f"itemFilter({index}).value"] = str(price_max)
    return FINDING_URL + "?" + urlencode(params)


def _trim(title: str, year: Optional[int], make: Optional[str], model: Optional[str]) -> Optional[str]:
    if year is None or not make or not model:
        return None
    pattern = re.compile(
        rf"^{year}\s+{re.escape(make)}\s+{re.escape(model)}\s*(.*)$",
        re.IGNORECASE,
    )
    match = pattern.match(title.strip())
    if not match:
        return None
    rest = _MILEAGE_RE.sub("", match.group(1)).strip(" -")
    return rest or None


def _mileage(title: str) -> Optional[int]:
    match = _MILEAGE_RE.search(title)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _region(location: Optional[str]) -> Optional[str]:
    if not location or "," not in location:
        return None
    token = location.split(",")[-1].strip().split()[-1]
    if len(token) == 2 and token.isalpha():
        return token.upper()
    return None


def _coordinates(item: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    lat = _float(_first(item.get("latitude") or item.get("lat")))
    lng = _float(_first(item.get("longitude") or item.get("lng") or item.get("lon")))
    if lat is None or lng is None:
        return None, None
    return lat, lng


def _price(item: dict[str, Any]) -> tuple[Optional[float], str]:
    selling = _first(item.get("sellingStatus"))
    if not isinstance(selling, dict):
        return None, "USD"
    current = _first(selling.get("currentPrice"))
    if not isinstance(current, dict):
        return None, "USD"
    raw = current.get("__value__")
    if raw is None:
        raw = current.get("value")
    currency = str(current.get("@currencyId") or "USD")
    return _float(raw), currency


def _time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _text(value: Any) -> Optional[str]:
    raw = _first(value)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value
