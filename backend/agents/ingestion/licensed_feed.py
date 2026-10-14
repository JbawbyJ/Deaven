"""Licensed listing feeds. No vendor client lives here.

LicensedFeedSource is the shared interface: fetch one page, map each record
onto a NormalizedListing, and walk pagination behind a rate limiter.

Two loaders share that interface. A paged REST JSON API is the shape used by
feeds such as MarketCheck and Auto.dev. A bulk file drop, such as a nightly
XML file, is the shape used by feeds such as DataOne. Field paths come from
config. Credentials and locations come from env:

- LICENSED_FEED_BASE_URL and LICENSED_FEED_API_KEY for the JSON feed
- LICENSED_FEED_XML_PATH or LICENSED_FEED_XML_URL for the XML drop

The JSON feed and an XML URL join the live-fetch list only when those env
vars are set. A local XML path is not a live fetch. BaT, classic.com, and
TCV stay parser-only. eBay Browse stays a live source either way.

shared.schemas.deal.DealSource has no licensed-feed member, and this package
does not edit shared/. Each provider still registers a #8 Source. The catalog
code is MANUAL, the non-vendor code. The feed id is the listing's source
string, and registered_feed_sources() returns that Source.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from shared.schemas.deal import DealSource
from shared.schemas.listing import (
    ListingLocation,
    NormalizedListing,
    SellerType,
    build_provenance,
    url_photo,
)
from shared.schemas.market import PriceKind, PriceObservation, Source
from shared.vin import vin_key

from backend.agents.ingestion.policy import USER_AGENT, RateLimiter, SourcePolicy

JSON_FEED_ID = "licensed_feed"
XML_FEED_ID = "licensed_feed_xml"
_ENV_BASE_URL = "LICENSED_FEED_BASE_URL"
_ENV_API_KEY = "LICENSED_FEED_API_KEY"
_ENV_XML_URL = "LICENSED_FEED_XML_URL"
_ENV_XML_PATH = "LICENSED_FEED_XML_PATH"

_REGISTRY: dict[str, Source] = {}


class MissingLicensedFeedCredentials(RuntimeError):
    """A licensed feed is not configured. No loader was called."""


@dataclass(frozen=True)
class FeedTarget:
    """One page or one file. url and path are the two delivery locations."""

    url: str | None = None
    path: str | None = None
    headers: Mapping[str, str] | None = None
    params: Mapping[str, str] | None = None


class FeedLoader(ABC):
    """Reads bytes for a FeedTarget. JSON and XML providers both use this."""

    @abstractmethod
    def load(self, target: FeedTarget) -> bytes:
        """Return the raw page or file. Callers parse it."""


class UrllibFeedLoader(FeedLoader):
    """Live HTTP loader. Tests inject a different loader and never call this."""

    def load(self, target: FeedTarget) -> bytes:
        if target.path and not target.url:
            return Path(target.path).read_bytes()
        if not target.url:
            raise ValueError("licensed feed URL is not set")
        url = target.url
        if target.params:
            url = f"{url}?{urllib.parse.urlencode(target.params)}"
        request = urllib.request.Request(
            url,
            headers=dict(target.headers or {}),
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()


class PathLoader(FeedLoader):
    """Read a local file drop. This does not open a socket."""

    def load(self, target: FeedTarget) -> bytes:
        if not target.path:
            raise ValueError("licensed feed path is not set")
        return Path(target.path).read_bytes()


@dataclass(frozen=True)
class FeedPage:
    listings: list[NormalizedListing]
    prices: list[PriceObservation]
    next_cursor: str | None
    source: Source


@dataclass(frozen=True)
class MappedRecord:
    listing: NormalizedListing
    prices: list[PriceObservation]


def registered_feed_sources() -> dict[str, Source]:
    """Feed id to the #8 Source registered by the last provider with that id."""
    return dict(_REGISTRY)


def json_feed_configured() -> bool:
    return bool(_env(_ENV_BASE_URL) and _env(_ENV_API_KEY))


def xml_feed_configured() -> bool:
    return bool(_env(_ENV_XML_PATH) or _env(_ENV_XML_URL))


def licensed_feed_policies() -> list[SourcePolicy]:
    """Live policies for configured network feeds. Empty when env is unset."""
    policies: list[SourcePolicy] = []
    base_url = _env(_ENV_BASE_URL)
    if base_url and _env(_ENV_API_KEY) and _is_http(base_url):
        policies.append(_policy(base_url, "Licensed JSON feed", _ENV_BASE_URL, _ENV_API_KEY))
    xml_url = _env(_ENV_XML_URL)
    if xml_url and not _env(_ENV_XML_PATH) and _is_http(xml_url):
        policies.append(_policy(xml_url, "Licensed XML feed", _ENV_XML_URL))
    return policies


class LicensedFeedSource(ABC):
    """One licensed provider. Fetch a page, map records, then follow pages."""

    def __init__(self, config: dict[str, Any], *, clock=time.monotonic, sleep=time.sleep) -> None:
        self.config = config
        self.feed_id = str(_required(config, "id")).strip()
        self.feed_name = str(_required(config, "name")).strip()
        self.seller_type = SellerType(str(config.get("seller_type") or SellerType.MARKETPLACE.value))
        self.page_size = int(config.get("page_size") or 50)
        self.max_pages = int(config.get("max_pages") or 20)
        self.fields = dict(_required(config, "fields"))
        for key in ("year", "make", "model", "asking_price", "url"):
            if not self.fields.get(key):
                raise ValueError(f"licensed feed field mapping missing {key}")
        interval = float(config.get("min_interval_seconds") or 2.0)
        self.limiter = RateLimiter(interval, clock=clock, sleep=sleep)
        self._source: Source | None = None

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """False when the credentials or file location for this provider are absent."""

    @property
    def source(self) -> Source:
        if self._source is None:
            raise MissingLicensedFeedCredentials(f"{self.feed_name} is disabled")
        return self._source

    @abstractmethod
    def fetch_page(self, *, cursor: str | None = None, fetched_at: datetime) -> FeedPage:
        """One page of listings. Disabled providers raise before any load."""

    @abstractmethod
    def map_record(self, record: Any, *, fetched_at: datetime) -> MappedRecord | None:
        """Map one raw record. Asking price stays the listing price."""

    def fetch_all(self, *, fetched_at: datetime) -> FeedPage:
        """Walk next_cursor until the feed ends. Each page is rate limited."""
        listings: list[NormalizedListing] = []
        prices: list[PriceObservation] = []
        cursor: str | None = None
        seen: set[str] = set()
        source = self.source
        for _ in range(self.max_pages):
            page = self.fetch_page(cursor=cursor, fetched_at=fetched_at)
            listings.extend(page.listings)
            prices.extend(page.prices)
            source = page.source
            nxt = page.next_cursor
            if not nxt or nxt in seen:
                break
            seen.add(nxt)
            cursor = nxt
        return FeedPage(listings=listings, prices=prices, next_cursor=None, source=source)

    def _register(self, base_url: str) -> Source:
        source = Source(
            code=DealSource.MANUAL,
            kind=self.seller_type,
            name=self.feed_name,
            base_url=base_url,
            robots_ok=False,
            tos_reviewed=False,
        )
        self._source = source
        _REGISTRY[self.feed_id] = source
        return source

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise MissingLicensedFeedCredentials(f"{self.feed_name} is disabled")


class JsonFeedProvider(LicensedFeedSource):
    """Config-mapped JSON pages. The loader returns one response body per page."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        base_url: str,
        api_key: str,
        loader: FeedLoader | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        super().__init__(config, clock=clock, sleep=sleep)
        self.base_url = base_url.strip()
        self.api_key = api_key.strip()
        self.records_path = str(_required(config, "records_path"))
        self.next_path = str(config.get("next_path") or "")
        self.page_param = str(config.get("page_param") or "page")
        self.page_size_param = str(config.get("page_size_param") or "page_size")
        self.path = str(config.get("path") or "/listings")
        self.loader = loader or UrllibFeedLoader()
        if self.enabled:
            self._register(_http_base(self.base_url, _ENV_BASE_URL))

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and _is_http(self.base_url))

    @classmethod
    def from_env(
        cls,
        config: dict[str, Any],
        *,
        loader: FeedLoader | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> JsonFeedProvider:
        base_url = _env(_ENV_BASE_URL)
        api_key = _env(_ENV_API_KEY)
        if not base_url or not api_key:
            raise MissingLicensedFeedCredentials(
                f"{_ENV_BASE_URL} and {_ENV_API_KEY} are required"
            )
        return cls(config, base_url=base_url, api_key=api_key, loader=loader, clock=clock, sleep=sleep)

    def fetch_page(self, *, cursor: str | None = None, fetched_at: datetime) -> FeedPage:
        self._require_enabled()
        self.limiter.acquire()
        target = self._target(cursor)
        payload = json.loads(self.loader.load(target).decode())
        rows = _dig(payload, self.records_path)
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise ValueError("licensed feed records_path must point at a list")
        listings: list[NormalizedListing] = []
        prices: list[PriceObservation] = []
        for row in rows:
            mapped = self.map_record(row, fetched_at=fetched_at)
            if mapped is None:
                continue
            listings.append(mapped.listing)
            prices.extend(mapped.prices)
        return FeedPage(
            listings=listings,
            prices=prices,
            next_cursor=_next_cursor(payload, self.next_path) if rows else None,
            source=self.source,
        )

    def map_record(self, record: Any, *, fetched_at: datetime) -> MappedRecord | None:
        if not isinstance(record, dict):
            return None
        return _map_flat(
            record,
            fields=self.fields,
            feed_id=self.feed_id,
            source=self.source,
            fetched_at=fetched_at,
            provenance_extra={"record": record},
        )

    def _target(self, cursor: str | None) -> FeedTarget:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": USER_AGENT,
        }
        if cursor and cursor.startswith(("http://", "https://")):
            return FeedTarget(url=cursor, headers=headers, params={})
        params = {
            self.page_param: cursor or "1",
            self.page_size_param: str(self.page_size),
        }
        url = self.base_url.rstrip("/") + "/" + self.path.lstrip("/")
        return FeedTarget(url=url, headers=headers, params=params)


class XmlFeedProvider(LicensedFeedSource):
    """Config-mapped XML file drop. One load, then pages of records."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        base_url: str,
        path: str = "",
        url: str = "",
        loader: FeedLoader | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        super().__init__(config, clock=clock, sleep=sleep)
        self.base_url = base_url.strip()
        self.file_path = path.strip()
        self.file_url = url.strip()
        self.record_tag = str(_required(config, "record_tag"))
        if loader is not None:
            self.loader = loader
        elif self.file_path:
            self.loader = PathLoader()
        else:
            self.loader = UrllibFeedLoader()
        self._cached: list[tuple[dict[str, str], str]] | None = None
        if self.enabled:
            self._register(_http_base(self.base_url, "base_url"))

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and _is_http(self.base_url) and (self.file_path or self.file_url))

    @classmethod
    def from_env(
        cls,
        config: dict[str, Any],
        *,
        loader: FeedLoader | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> XmlFeedProvider:
        path = _env(_ENV_XML_PATH)
        url = _env(_ENV_XML_URL)
        if not path and not url:
            raise MissingLicensedFeedCredentials(
                f"{_ENV_XML_PATH} or {_ENV_XML_URL} is required"
            )
        base_url = str(config.get("base_url") or "")
        if not base_url and url and _is_http(url):
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        if not base_url:
            raise MissingLicensedFeedCredentials("licensed XML feed base_url is required")
        return cls(
            config,
            base_url=base_url,
            path=path,
            url="" if path else url,
            loader=loader,
            clock=clock,
            sleep=sleep,
        )

    def fetch_page(self, *, cursor: str | None = None, fetched_at: datetime) -> FeedPage:
        self._require_enabled()
        self.limiter.acquire()
        rows = self._rows()
        page_index = int(cursor or "1")
        if page_index < 1:
            raise ValueError("licensed feed page cursor must be >= 1")
        start = (page_index - 1) * self.page_size
        chunk = rows[start : start + self.page_size]
        listings: list[NormalizedListing] = []
        prices: list[PriceObservation] = []
        for record, row_xml in chunk:
            mapped = self.map_record(
                {"record": record, "record_xml": row_xml},
                fetched_at=fetched_at,
            )
            if mapped is None:
                continue
            listings.append(mapped.listing)
            prices.extend(mapped.prices)
        next_cursor = str(page_index + 1) if start + self.page_size < len(rows) else None
        return FeedPage(
            listings=listings,
            prices=prices,
            next_cursor=next_cursor,
            source=self.source,
        )

    def map_record(self, record: Any, *, fetched_at: datetime) -> MappedRecord | None:
        if not isinstance(record, dict):
            return None
        flat = record.get("record")
        row_xml = record.get("record_xml")
        if not isinstance(flat, dict) or not isinstance(row_xml, str):
            return None
        return _map_flat(
            flat,
            fields=self.fields,
            feed_id=self.feed_id,
            source=self.source,
            fetched_at=fetched_at,
            provenance_extra={"record": flat, "record_xml": row_xml},
        )

    def _rows(self) -> list[tuple[dict[str, str], str]]:
        if self._cached is None:
            raw = self.loader.load(FeedTarget(url=self.file_url or None, path=self.file_path or None))
            self._cached = _xml_rows(raw, self.record_tag)
        return self._cached


def _map_flat(
    record: Mapping[str, Any],
    *,
    fields: Mapping[str, str],
    feed_id: str,
    source: Source,
    fetched_at: datetime,
    provenance_extra: dict[str, Any],
) -> MappedRecord | None:
    asking = _money(record.get(fields["asking_price"]))
    source_url = _text(record.get(fields["url"]))
    year = _year(record.get(fields["year"]))
    make = _text(record.get(fields["make"]))
    model = _text(record.get(fields["model"]))
    if asking is None or not source_url or year is None or not make or not model:
        return None
    sold = _money(record.get(fields["sold_price"])) if fields.get("sold_price") else None
    raw_vin = _text(record.get(fields["vin"])) if fields.get("vin") else None
    normalized_vin = vin_key(raw_vin) if raw_vin else None
    mileage = _miles(record.get(fields["mileage"])) if fields.get("mileage") else None
    currency = (_text(record.get(fields["currency"])) if fields.get("currency") else None) or "USD"
    city = _text(record.get(fields["city"])) if fields.get("city") else None
    region = _text(record.get(fields["region"])) if fields.get("region") else None
    postal = _text(record.get(fields["postal_code"])) if fields.get("postal_code") else None
    country = _country(record.get(fields["country"])) if fields.get("country") else None
    title = _text(record.get(fields["title"])) if fields.get("title") else None
    trim = _text(record.get(fields["trim"])) if fields.get("trim") else None
    photo = _text(record.get(fields["photo"])) if fields.get("photo") else None
    when = _aware(fetched_at)
    listing = NormalizedListing(
        vin=normalized_vin,
        year=year,
        make=make,
        model=model,
        trim=trim,
        mileage=mileage,
        price=asking,
        currency=currency,
        location=ListingLocation(
            label=_label(city, region, postal),
            city=city,
            region=region,
            country=country,
        ),
        seller_type=source.kind,
        source=feed_id,
        source_url=source_url,
        title=title,
        photos=[url_photo(photo)] if photo and photo.startswith(("http://", "https://")) else [],
        first_seen=when,
        last_seen=when,
        provenance=build_provenance(
            source=feed_id,
            source_url=source_url,
            fetched_at=when,
            payload={
                "feed_id": feed_id,
                "source_name": source.name,
                "source_code": source.code.value,
                **provenance_extra,
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
    if sold is not None:
        prices.append(
            PriceObservation(
                listing_id=listing.observation_id,
                observed_at=listing.provenance.fetched_at,
                amount=sold,
                currency=listing.currency,
                kind=PriceKind.SOLD,
            )
        )
    return MappedRecord(listing=listing, prices=prices)


def _xml_rows(raw: bytes, record_tag: str) -> list[tuple[dict[str, str], str]]:
    root = ET.fromstring(raw)
    rows: list[tuple[dict[str, str], str]] = []
    for element in root.iter(record_tag):
        flat = {child.tag: (child.text or "").strip() for child in list(element)}
        rows.append((flat, ET.tostring(element, encoding="unicode")))
    return rows


def _policy(url: str, name: str, *env_names: str) -> SourcePolicy:
    names = " and ".join(env_names)
    verb = "are" if len(env_names) > 1 else "is"
    return SourcePolicy(
        code=DealSource.MANUAL,
        user_agent=USER_AGENT,
        min_interval_seconds=2.0,
        tos_note=(
            f"{name} is a contracted feed, not a site scrape. "
            f"Live only when {names} {verb} set. No vendor is selected."
        ),
        tos_url=url,
        live_fetch_allowed=True,
        review_status="licensed feed",
    )


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _required(config: Mapping[str, Any], key: str) -> Any:
    value = config.get(key)
    if value in (None, ""):
        raise ValueError(f"licensed feed config missing {key}")
    return value


def _dig(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _next_cursor(payload: Any, path: str) -> str | None:
    if not path:
        return None
    value = _dig(payload, path)
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _is_http(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _http_base(url: str, label: str) -> str:
    if not _is_http(url):
        raise ValueError(f"{label} must be an http(s) URL")
    return url.strip()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _year(value: Any) -> int | None:
    text = _text(value)
    if text is None:
        return None
    return int(text)


def _miles(value: Any) -> int | None:
    text = _text(value)
    if text is None:
        return None
    return int(text.replace(",", ""))


def _money(value: Any) -> float | None:
    text = _text(value)
    if text is None:
        return None
    amount = float(text.replace(",", ""))
    if amount < 0 or amount != amount or amount == float("inf"):
        raise ValueError("price must be finite and >= 0")
    return amount


def _country(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    code = text.upper()
    if len(code) == 2 and code.isalpha():
        return code
    return None


def _label(city: str | None, region: str | None, postal: str | None) -> str | None:
    if city and region and postal:
        return f"{city}, {region} {postal}"
    if city and region:
        return f"{city}, {region}"
    return city or region


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("fetched_at must be timezone-aware")
    return value
