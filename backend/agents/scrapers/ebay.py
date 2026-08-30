"""
backend/agents/scrapers/ebay.py
eBay Motors scraper via the Finding API (App ID auth, no OAuth).
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

from shared.schemas.deal import ListingData, WatchlistFilter

logger = logging.getLogger(__name__)

_backend_dir = Path(__file__).resolve().parents[2]
load_dotenv(_backend_dir / ".env")
load_dotenv(_backend_dir.parent / ".env", override=False)

FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
MOTORS_CATEGORY_ID = "6001"
GLOBAL_ID = "EBAY-MOTOR"
ENTRIES_PER_PAGE = 100
MAX_PAGES = 5

_YEAR_MAKE_MODEL_RE = re.compile(
    r"^(\d{4})\s+([A-Za-z][\w-]+)\s+([A-Za-z0-9][\w-]+)",
    re.IGNORECASE,
)


def finding_keywords(filters: WatchlistFilter) -> str:
    """
    Finding API keywords for a watchlist.

    E46 M3 hunts (BMW + M3, years overlapping 1999–2006) get a dedicated
    "E46" token so chassis search is not just year numbers.
    """
    parts: list[str] = []
    makes = list(filters.makes or [])
    models = list(filters.models or [])
    parts.extend(makes)
    parts.extend(models)
    blob = " ".join(makes + models).lower()
    year_min = filters.year_min
    year_max = filters.year_max
    e46 = (
        "bmw" in blob
        and "m3" in blob
        and (year_min is None or year_min <= 2006)
        and (year_max is None or year_max >= 1999)
        and (year_min is None or year_min >= 1998)
        and (year_max is None or year_max <= 2007)
    )
    if e46:
        parts.append("E46")
    else:
        if year_min:
            parts.append(str(year_min))
        if year_max and year_max != year_min:
            parts.append(str(year_max))
    return " ".join(parts).strip()


def extract_year_make_model(title: str) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """
    Parse vehicle year, make, and model from a listing title.

    Example: "2003 BMW M3 Coupe" → (2003, "BMW", "M3")
    """
    match = _YEAR_MAKE_MODEL_RE.match(title.strip())
    if not match:
        return None, None, None
    return int(match.group(1)), match.group(2), match.group(3)


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class EbayMotorsScraper:
    """eBay Motors listings via the Finding API findItemsAdvanced operation."""

    def __init__(self, app_id: Optional[str] = None) -> None:
        self.app_id = app_id or os.getenv("EBAY_APP_ID")
        if not self.app_id:
            logger.warning("EBAY_APP_ID is not set — eBay scraper will return no results")

    async def fetch_listings(self, filters: WatchlistFilter) -> list[dict]:
        """Search eBay Motors category 6001 and return raw item dicts."""
        if not self.app_id:
            logger.error("Cannot fetch eBay listings without EBAY_APP_ID")
            return []

        keywords = self._build_keywords(filters)
        if not keywords:
            logger.warning("WatchlistFilter has no makes/models — skipping eBay search")
            return []

        all_items: list[dict] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(1, MAX_PAGES + 1):
                try:
                    params = self._build_request_params(filters, keywords, page)
                    response = await client.get(FINDING_API_URL, params=params)
                    response.raise_for_status()
                    data = response.json()
                except httpx.HTTPStatusError as e:
                    logger.error(
                        "eBay Finding API HTTP %s: %s",
                        e.response.status_code,
                        e.response.text[:500],
                    )
                    break
                except httpx.RequestError as e:
                    logger.error("eBay Finding API request failed: %s", e)
                    break
                except ValueError as e:
                    logger.error("eBay Finding API returned invalid JSON: %s", e)
                    break

                items = self._extract_items(data)
                if not items:
                    break

                for item in items:
                    item_id = str(_first(item.get("itemId")) or "")
                    if item_id and item_id in seen_ids:
                        continue
                    if item_id:
                        seen_ids.add(item_id)
                    all_items.append(item)

                if len(items) < ENTRIES_PER_PAGE:
                    break

        logger.info("eBay Motors: fetched %d listings for '%s'", len(all_items), keywords)
        return all_items

    def parse_listing(self, raw: dict) -> Optional[ListingData]:
        """Convert a raw Finding API item dict into ListingData."""
        try:
            title = str(_first(raw.get("title")) or "").strip()
            if not title:
                logger.debug("Skipping eBay item with empty title")
                return None

            price = self._extract_price(raw)
            if price is None or price <= 0:
                logger.debug("Skipping eBay item %s — invalid price", _first(raw.get("itemId")))
                return None

            year, make, model = extract_year_make_model(title)
            location = _first(raw.get("location"))
            if location is not None:
                location = str(location)

            end_date = self._extract_end_date(raw)
            listing_date = self._extract_listing_date(raw)

            return ListingData(
                title=title,
                price=price,
                year=year,
                make=make,
                model=model,
                location=location,
                seller_type="private",
                listing_date=listing_date,
                end_date=end_date,
            )
        except Exception as e:
            logger.warning(
                "Failed to parse eBay listing %s: %s",
                _first(raw.get("itemId")),
                e,
            )
            return None

    @staticmethod
    def extract_images(raw: dict) -> list[str]:
        """Pull image URLs from pictureURLSuperSize or galleryURL."""
        for key in ("pictureURLSuperSize", "galleryURL"):
            urls = raw.get(key)
            if not urls:
                continue
            if isinstance(urls, str):
                return [urls]
            return [str(u) for u in _as_list(urls) if u]
        return []

    @staticmethod
    def extract_url(raw: dict) -> Optional[str]:
        url = _first(raw.get("viewItemURL"))
        return str(url) if url else None

    def _build_keywords(self, filters: WatchlistFilter) -> str:
        return finding_keywords(filters)

    def _build_request_params(
        self,
        filters: WatchlistFilter,
        keywords: str,
        page: int,
    ) -> dict[str, str]:
        params: dict[str, str] = {
            "OPERATION-NAME": "findItemsAdvanced",
            "SERVICE-VERSION": "1.0.0",
            "SECURITY-APPNAME": self.app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "",
            "GLOBAL-ID": GLOBAL_ID,
            "categoryId": MOTORS_CATEGORY_ID,
            "keywords": keywords,
            "paginationInput.entriesPerPage": str(ENTRIES_PER_PAGE),
            "paginationInput.pageNumber": str(page),
            "sortOrder": "StartTimeNewest",
        }
        params.update(self._item_filter_params(filters))
        params.update(self._aspect_filter_params(filters))
        return params

    @staticmethod
    def _item_filter_params(filters: WatchlistFilter) -> dict[str, str]:
        params: dict[str, str] = {}
        idx = 0

        params[f"itemFilter({idx}).name"] = "Condition"
        params[f"itemFilter({idx}).value"] = "Used"
        idx += 1

        params[f"itemFilter({idx}).name"] = "ListingType"
        params[f"itemFilter({idx}).value(0)"] = "Auction"
        params[f"itemFilter({idx}).value(1)"] = "FixedPrice"
        idx += 1

        if filters.price_min is not None:
            params[f"itemFilter({idx}).name"] = "MinPrice"
            params[f"itemFilter({idx}).value"] = str(int(filters.price_min))
            params[f"itemFilter({idx}).paramName"] = "Currency"
            params[f"itemFilter({idx}).paramValue"] = "USD"
            idx += 1

        if filters.price_max is not None:
            params[f"itemFilter({idx}).name"] = "MaxPrice"
            params[f"itemFilter({idx}).value"] = str(int(filters.price_max))
            params[f"itemFilter({idx}).paramName"] = "Currency"
            params[f"itemFilter({idx}).paramValue"] = "USD"
            idx += 1

        return params

    @staticmethod
    def _aspect_filter_params(filters: WatchlistFilter) -> dict[str, str]:
        if filters.year_min is None and filters.year_max is None:
            return {}

        year_min = filters.year_min or filters.year_max
        year_max = filters.year_max or filters.year_min
        if year_min is None or year_max is None:
            return {}

        span = year_max - year_min + 1
        if span > 30:
            year_values = f"{year_min}|{year_max}"
        else:
            year_values = "|".join(str(y) for y in range(year_min, year_max + 1))

        return {
            "aspectFilter(0).aspectName": "Model Year",
            "aspectFilter(0).aspectValueName": year_values,
        }

    @staticmethod
    def _extract_items(data: dict) -> list[dict]:
        try:
            response = data["findItemsAdvancedResponse"][0]
        except (KeyError, IndexError, TypeError):
            logger.error("eBay response missing findItemsAdvancedResponse")
            return []

        ack = _first(response.get("ack"))
        if ack not in ("Success", "Warning"):
            errors = response.get("errorMessage", [])
            logger.error("eBay Finding API error (ack=%s): %s", ack, errors)
            return []

        search_result = _first(response.get("searchResult"))
        if not search_result:
            return []

        items = search_result.get("item")
        if not items:
            return []
        if isinstance(items, dict):
            return [items]
        return list(items)

    @staticmethod
    def _extract_price(raw: dict) -> Optional[float]:
        selling_status = _first(raw.get("sellingStatus"))
        if not isinstance(selling_status, dict):
            return None

        current_price = _first(selling_status.get("currentPrice"))
        if not isinstance(current_price, dict):
            return None

        value = current_price.get("__value__") or current_price.get("value")
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _extract_end_date(raw: dict) -> Optional[datetime]:
        listing_info = _first(raw.get("listingInfo"))
        if not isinstance(listing_info, dict):
            return None

        listing_type = str(_first(listing_info.get("listingType")) or "")
        if listing_type not in ("Auction", "AuctionWithBIN"):
            return None

        end_time = _first(listing_info.get("endTime"))
        if not end_time:
            return None

        return EbayMotorsScraper._parse_ebay_datetime(str(end_time))

    @staticmethod
    def _extract_listing_date(raw: dict) -> Optional[datetime]:
        listing_info = _first(raw.get("listingInfo"))
        if not isinstance(listing_info, dict):
            return None

        start_time = _first(listing_info.get("startTime"))
        if not start_time:
            return None

        return EbayMotorsScraper._parse_ebay_datetime(str(start_time))

    @staticmethod
    def _parse_ebay_datetime(value: str) -> datetime:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
