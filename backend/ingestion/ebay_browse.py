"""
eBay Motors listings via the Browse API item_summary/search.

The Finding API is retired. This adapter uses an OAuth client-credentials
token from EBAY_CLIENT_ID and EBAY_CLIENT_SECRET, cached until it expires.
It does not scrape HTML. Tests pass a transport and fixture bodies.
"""

from __future__ import annotations

import base64
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
    decide_robots,
    default_transport,
    host_of,
    robots_url_for,
)
from shared.schemas.deal import ListingData
from shared.vin import is_valid_vin

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"
CARS_AND_TRUCKS_CATEGORY = "6001"
MARKETPLACE_ID = "EBAY_MOTORS"
_TOKEN_SKEW_S = 60.0
_MILEAGE_RE = re.compile(r"([\d,]+)\s*(?:mi|miles)\b", re.IGNORECASE)
_VIN_NAMES = {"vin", "vehicle identification number"}


class MissingCredentials(Exception):
    """EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required before any request."""


class EbayBrowseError(Exception):
    """The Browse API or token response could not be used."""


class EbayBrowseAdapter:
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        transport=None,
        min_interval_s: float = 1.0,
        clock=None,
        sleep=None,
        user_agent: str = USER_AGENT,
    ) -> None:
        if client_id is None:
            client_id = os.getenv("EBAY_CLIENT_ID", "")
        if client_secret is None:
            client_secret = os.getenv("EBAY_CLIENT_SECRET", "")
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self._transport = transport or default_transport
        self._user_agent = user_agent
        self._clock = clock or _monotonic
        self._limiter = DomainRateLimiter(min_interval_s, clock=self._clock, sleep=sleep)
        self._robots_body: dict[str, str] = {}
        self._token = ""
        self._token_expires_at = 0.0

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
        if not self.client_id or not self.client_secret:
            raise MissingCredentials(
                "Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET to call the eBay Browse API"
            )

        search_url = _search_url(query, price_min, price_max)
        host = host_of(search_url)
        if host_of(TOKEN_URL) != host:
            raise EbayBrowseError("token and search hosts must match")
        delay = self._assert_allowed(host, search_url)
        token = self._access_token(host, delay)
        self._limiter.acquire(host, crawl_delay_s=delay)
        status, body = self._request(
            search_url,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE_ID,
                "Accept": "application/json",
            },
        )
        if status != 200:
            raise EbayBrowseError(f"Browse API HTTP {status}")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise EbayBrowseError("Browse API returned invalid JSON") from exc
        return parse_browse_response(payload)

    def _assert_allowed(self, host: str, search_url: str) -> float:
        search = self._load_robots(host, search_url)
        token = decide_robots(self._robots_body[host], self._user_agent, TOKEN_URL)
        if not search.allowed:
            raise RobotsDisallowed(search_url, search.reason)
        if not token.allowed:
            raise RobotsDisallowed(TOKEN_URL, token.reason)
        return max(search.crawl_delay_s, token.crawl_delay_s)

    def _access_token(self, host: str, crawl_delay_s: float) -> str:
        now = self._clock()
        if self._token and now < self._token_expires_at:
            return self._token
        self._limiter.acquire(host, crawl_delay_s=crawl_delay_s)
        status, body = self._request(
            TOKEN_URL,
            method="POST",
            headers={
                "Authorization": "Basic " + _basic_auth(self.client_id, self.client_secret),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body=urlencode(
                {"grant_type": "client_credentials", "scope": OAUTH_SCOPE}
            ).encode(),
        )
        if status != 200:
            raise EbayBrowseError(f"OAuth token HTTP {status}")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise EbayBrowseError("OAuth token response was not JSON") from exc
        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not token or isinstance(token, bool) or not isinstance(expires_in, (int, float)):
            raise EbayBrowseError("OAuth token response is missing access_token or expires_in")
        lifetime = float(expires_in)
        if lifetime <= 0:
            raise EbayBrowseError("OAuth token expires_in must be positive")
        skew = min(_TOKEN_SKEW_S, lifetime / 2)
        self._token = str(token)
        self._token_expires_at = self._clock() + (lifetime - skew)
        return self._token

    def _load_robots(self, host: str, url: str):
        body = self._robots_body.get(host)
        if body is None:
            self._limiter.acquire(host)
            status, body = self._request(robots_url_for(url))
            if status != 200:
                raise RobotsDisallowed(robots_url_for(url), "robots_unavailable")
            self._robots_body[host] = body
        return decide_robots(body, self._user_agent, url)

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        body: bytes | None = None,
    ) -> tuple[int, str]:
        merged = {"User-Agent": self._user_agent}
        if headers:
            merged.update(headers)
        return self._transport(url, merged, method, body)


def parse_browse_response(payload: dict[str, Any]) -> list[ListingData]:
    if not isinstance(payload, dict):
        raise EbayBrowseError("Browse API response was not an object")
    if "itemSummaries" not in payload:
        if payload.get("errors"):
            raise EbayBrowseError("Browse API returned errors")
        raise EbayBrowseError("Browse API response is missing itemSummaries")
    items = payload.get("itemSummaries") or []
    if isinstance(items, dict):
        items = [items]
    listings: list[ListingData] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        listing = _listing_from_summary(item)
        if listing is not None:
            listings.append(listing)
    return listings


def _listing_from_summary(item: dict[str, Any]) -> Optional[ListingData]:
    item_id = str(item.get("itemId") or "").strip()
    title = str(item.get("title") or "").strip()
    url = str(item.get("itemWebUrl") or "").strip()
    price, currency = _price(item)
    if not item_id or not title or not url or price is None or price <= 0:
        return None

    year, make, model = extract_year_make_model(title)
    location, region, postal, lat, lng = _location(item)
    vin = _vin(item)
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
        "region": region,
        "zip": postal,
        "listing_date": _time(_text(item.get("itemCreationDate"))),
        "source": "ebay",
        "source_id": item_id,
    }
    if lat is not None and lng is not None:
        fields["lat"] = lat
        fields["lng"] = lng
    return ListingData(**fields)


def _search_url(keywords: str, price_min: Optional[float], price_max: Optional[float]) -> str:
    params = {
        "q": keywords,
        "category_ids": CARS_AND_TRUCKS_CATEGORY,
        "limit": "20",
        "sort": "newlyListed",
        "filter": _filter(price_min, price_max),
    }
    return SEARCH_URL + "?" + urlencode(params)


def _filter(price_min: Optional[float], price_max: Optional[float]) -> str:
    parts = ["conditions:{USED}"]
    if price_min is not None or price_max is not None:
        low = "" if price_min is None else _number(price_min)
        high = "" if price_max is None else _number(price_max)
        parts.append(f"price:[{low}..{high}]")
        parts.append("priceCurrency:USD")
    return ",".join(parts)


def _number(value: float) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return str(number)


def _location(
    item: dict[str, Any],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[float], Optional[float]]:
    raw = item.get("itemLocation")
    if not isinstance(raw, dict):
        return None, None, None, None, None
    city = _text(raw.get("city"))
    region = _text(raw.get("stateOrProvince"))
    postal = _text(raw.get("postalCode"))
    label = ", ".join(part for part in (city, region) if part) or None
    lat = _float(raw.get("latitude"))
    lng = _float(raw.get("longitude"))
    if lat is None or lng is None:
        lat, lng = None, None
    return label, region, postal, lat, lng


def _vin(item: dict[str, Any]) -> Optional[str]:
    aspects = item.get("localizedAspects")
    if aspects is None:
        aspects = item.get("aspects")
    values: list[Any] = []
    if isinstance(aspects, list):
        for aspect in aspects:
            if not isinstance(aspect, dict):
                continue
            name = str(aspect.get("name") or "").strip().lower()
            if name in _VIN_NAMES:
                values.append(aspect.get("value"))
    elif isinstance(aspects, dict):
        for name, value in aspects.items():
            if str(name).strip().lower() in _VIN_NAMES:
                values.append(value)
    for value in values:
        if isinstance(value, list):
            value = value[0] if value else None
        if value is None:
            continue
        text = str(value).strip()
        if text and is_valid_vin(text):
            return text
    return None


def _price(item: dict[str, Any]) -> tuple[Optional[float], str]:
    raw = item.get("price")
    if not isinstance(raw, dict):
        raw = item.get("currentBidPrice")
    if not isinstance(raw, dict):
        return None, "USD"
    currency = str(raw.get("currency") or "USD")
    return _float(raw.get("value")), currency


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


def _time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _basic_auth(client_id: str, client_secret: str) -> str:
    token = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
    return token


def _monotonic() -> float:
    import time

    return time.monotonic()
