"""
backend/agents/scrapers/tcv.py
TCV (tc-v.com) JDM vehicle scraper — Japanese export stock listings.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import anthropic
import httpx
from dotenv import load_dotenv
from playwright.async_api import Browser, Page, async_playwright

from shared.schemas.deal import ListingData, WatchlistFilter

logger = logging.getLogger(__name__)

_backend_dir = Path(__file__).resolve().parents[2]
load_dotenv(_backend_dir / ".env")
load_dotenv(_backend_dir.parent / ".env", override=False)

BASE_URL = "https://www.tc-v.com"
STOCK_SEARCH_URL = f"{BASE_URL}/stock/"
FX_API_URL = "https://api.exchangerate-api.com/v4/latest/JPY"
MAX_PAGES = 10
FX_CACHE_TTL = 3600
KM_TO_MILES = 0.621371
IMPORT_AGE_YEARS = 25

HAIKU_MODEL = "claude-3-5-haiku-20241022"
VISION_MODEL = "claude-3-5-haiku-20241022"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

_JPY_RE = re.compile(r"(?:¥|￥|JPY)\s*([\d,]+)", re.IGNORECASE)
_USD_RE = re.compile(r"(?:US\$|USD|\$)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_KM_RE = re.compile(r"([\d,]+)\s*(?:km|KM|ｋｍ|キロ)", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_JA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")
_STOCK_LINE_RE = re.compile(
    r"STOCK\s*(?P<year>19\d{2}|20\d{2})\s*(?P<make>[A-Za-z-]+)\s+(?P<model>.+?)\s+FOB\s+(?P<price>.+)$",
    re.IGNORECASE,
)
_CHASSIS_RE = re.compile(r"\b([A-Z]{1,3}\d{2,3}[- ]?[A-Z0-9]{2,6})\b")
_GRADE_RE = re.compile(r"\b([1-5](?:\.\d)?|R?B?)\b")

_LISTING_PARSE_PROMPT = """Parse this Japanese vehicle export listing text into JSON.
Return ONLY valid JSON with these keys (use null when unknown):
{
  "title": "English title",
  "year": 1998,
  "make": "Toyota",
  "model": "Supra",
  "price_jpy": 1500000,
  "mileage_km": 85000,
  "chassis_code": "JZA80",
  "auction_grade": "4.5",
  "location": "Japan"
}

Listing text:
"""

_AUCTION_SHEET_PROMPT = """You are an expert at reading Japanese vehicle auction sheets (USS/TAA/etc).
Extract structured data from this auction sheet image. Return ONLY valid JSON:
{
  "condition_grade": "4.5",
  "mileage_km": 85000,
  "color": "Pearl White",
  "equipment": ["AC", "PS", "PW", "AW"],
  "damage_notes": ["small scratch left rear door"],
  "chassis_code": "JZA80",
  "raw_notes": "brief English summary"
}
"""

_EXTRACT_DOM_LISTINGS_JS = """
() => {
  const listings = [];
  const seen = new Set();

  const push = (url, node) => {
    if (!url || seen.has(url)) return;
    if (!/\\/used_car\\/[^/]+\\/[^/]+\\/\\d+/.test(url)) return;
    seen.add(url);
    const card = node.closest('li, tr, article, div') || node;
    const text = (card.innerText || node.innerText || '').replace(/\\s+/g, ' ').trim();
    const img = card.querySelector('img')?.src || node.querySelector('img')?.src || null;
    listings.push({
      url,
      raw_text: text,
      images: img ? [img] : [],
    });
  };

  document.querySelectorAll('a[href*="/used_car/"]').forEach((a) => push(a.href, a));
  document.querySelectorAll('[data-href*="/used_car/"]').forEach((el) => {
    push(el.getAttribute('data-href'), el);
  });

  return listings;
}
"""


async def random_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


def pick_user_agent() -> str:
    return random.choice(USER_AGENTS)


def _slugify(value: str) -> str:
    return quote(value.strip().lower().replace(" ", "%20"))


class TCVScraper:
    """TCV (tc-v.com) JDM export listing scraper."""

    _fx_cache: dict[str, Any] = {"rate": None, "expires_at": 0.0}

    def __init__(self, anthropic_client: Optional[anthropic.AsyncAnthropic] = None) -> None:
        self.client = anthropic_client or anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )

    async def fetch_listings(self, filters: WatchlistFilter) -> list[dict]:
        combos = self._filter_combos(filters)
        if not combos:
            logger.warning("TCV: no make/model combinations in WatchlistFilter")
            return []

        all_listings: list[dict] = []
        seen_urls: set[str] = set()

        playwright = None
        browser = None
        try:
            playwright, browser, page = await self._launch()

            for make, model in combos:
                year_min = filters.year_min or 1980
                year_max = filters.year_max or datetime.now().year

                for page_num in range(1, MAX_PAGES + 1):
                    url = self._build_search_url(make, model, year_min, year_max, page_num)
                    if not await self._navigate(page, url):
                        break

                    batch = await self._extract_dom_listings(page)
                    if not batch:
                        if page_num == 1:
                            fallback = (
                                f"{BASE_URL}/used_car/{make.lower()}/"
                                f"{quote(model.lower())}/index.html"
                            )
                            if fallback != url and await self._navigate(page, fallback):
                                batch = await self._extract_dom_listings(page)
                        if not batch:
                            break

                    new_rows = 0
                    for raw in batch:
                        listing_url = raw.get("url") or ""
                        if not listing_url or listing_url in seen_urls:
                            continue

                        parsed = await self._parse_listing_text(raw.get("raw_text") or "")
                        merged = {**raw, **{k: v for k, v in parsed.items() if v is not None}}
                        merged.setdefault("url", listing_url)

                        year = merged.get("year")
                        if year and not self.check_import_eligibility(int(year)):
                            continue

                        if filters.price_min or filters.price_max:
                            usd = merged.get("price_usd")
                            if usd is None and merged.get("price_jpy"):
                                usd = await self.jpy_to_usd(float(merged["price_jpy"]))
                                merged["price_usd"] = usd
                            if usd is not None:
                                if filters.price_min and usd < filters.price_min:
                                    continue
                                if filters.price_max and usd > filters.price_max:
                                    continue

                        merged["import_eligible"] = True
                        seen_urls.add(listing_url)
                        all_listings.append(merged)
                        new_rows += 1

                    logger.debug(
                        "TCV %s %s page %d: %d new listings",
                        make,
                        model,
                        page_num,
                        new_rows,
                    )
                    if new_rows == 0:
                        break
                    if page_num < MAX_PAGES:
                        await random_delay()

        except Exception as e:
            logger.error("TCV fetch_listings failed: %s", e)
        finally:
            if playwright and browser:
                await self._close(playwright, browser)

        logger.info("TCV: fetched %d eligible listings", len(all_listings))
        return all_listings

    def parse_listing(self, raw: dict) -> Optional[ListingData]:
        try:
            year = raw.get("year")
            if year is not None:
                year = int(year)
                if not self.check_import_eligibility(year):
                    logger.debug("TCV listing rejected — import ineligible year %s", year)
                    return None

            jpy_price = raw.get("price_jpy") or raw.get("jpy_price")
            usd_price = raw.get("price_usd")
            if usd_price is None and jpy_price is not None:
                usd_price = self._jpy_to_usd_sync(float(jpy_price))
                raw["price_usd"] = usd_price

            title = str(raw.get("title") or raw.get("raw_text") or "").strip()
            if not title:
                return None

            mileage_km = raw.get("mileage_km") or raw.get("mileage")
            mileage_mi = None
            if mileage_km is not None:
                mileage_mi = int(float(mileage_km) * KM_TO_MILES)

            raw["chassis_code"] = raw.get("chassis_code")
            raw["auction_grade"] = raw.get("auction_grade")
            raw["jpy_price"] = float(jpy_price) if jpy_price is not None else None
            raw["import_eligible"] = True

            if usd_price is None:
                return None

            description_parts = []
            if raw.get("chassis_code"):
                description_parts.append(f"Chassis: {raw['chassis_code']}")
            if raw.get("auction_grade"):
                description_parts.append(f"Auction grade: {raw['auction_grade']}")
            if raw.get("jpy_price"):
                description_parts.append(f"JPY ¥{int(raw['jpy_price']):,}")

            return ListingData(
                title=title[:250],
                price=float(usd_price),
                mileage=mileage_mi,
                year=year,
                make=raw.get("make"),
                model=raw.get("model"),
                location=raw.get("location") or "Japan",
                description=" | ".join(description_parts) or None,
                seller_type="dealer",
            )
        except Exception as e:
            logger.warning("Failed to parse TCV listing: %s", e)
            return None

    async def parse_listing_async(self, raw: dict) -> Optional[ListingData]:
        """Async variant that converts JPY when needed."""
        if raw.get("price_usd") is None and raw.get("price_jpy"):
            raw["price_usd"] = await self.jpy_to_usd(float(raw["price_jpy"]))
        return self.parse_listing(raw)

    async def get_auction_sheet_data(self, sheet_url: str) -> dict:
        """Download auction sheet image and extract structured data via Claude Vision."""
        if not sheet_url:
            return {}

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
                response = await http.get(sheet_url)
                response.raise_for_status()
                image_bytes = response.content
                media_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
                if not media_type.startswith("image/"):
                    media_type = "image/jpeg"
        except Exception as e:
            logger.error("TCV auction sheet download failed for %s: %s", sheet_url, e)
            return {}

        try:
            message = await self.client.messages.create(
                model=VISION_MODEL,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                                },
                            },
                            {"type": "text", "text": _AUCTION_SHEET_PROMPT},
                        ],
                    }
                ],
            )
            raw_text = message.content[0].text
            data = json.loads(raw_text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as e:
            logger.error("TCV auction sheet JSON parse error: %s", e)
        except Exception as e:
            logger.error("TCV auction sheet vision error: %s", e)
        return {}

    @staticmethod
    def check_import_eligibility(year: int) -> bool:
        """US 25-year import rule."""
        current_year = datetime.now(timezone.utc).year
        return (current_year - int(year)) >= IMPORT_AGE_YEARS

    async def jpy_to_usd(self, amount: float) -> float:
        rate = await self._get_jpy_usd_rate()
        return round(float(amount) * rate, 2)

    def _jpy_to_usd_sync(self, amount: float) -> float:
        rate = self._fx_cache.get("rate") or 0.0067
        return round(float(amount) * float(rate), 2)

    async def _get_jpy_usd_rate(self) -> float:
        now = time.time()
        cached = self._fx_cache.get("rate")
        if cached and now < float(self._fx_cache.get("expires_at", 0)):
            return float(cached)

        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                response = await http.get(FX_API_URL)
                response.raise_for_status()
                data = response.json()
            rate = float(data["rates"]["USD"])
            self._fx_cache["rate"] = rate
            self._fx_cache["expires_at"] = now + FX_CACHE_TTL
            logger.debug("TCV FX rate refreshed: 1 JPY = %s USD", rate)
            return rate
        except Exception as e:
            logger.error("TCV FX rate fetch failed: %s", e)
            if cached:
                logger.warning("TCV using stale cached FX rate")
                return float(cached)
            return 0.0067  # conservative fallback ~150 JPY/USD

    @staticmethod
    def _filter_combos(filters: WatchlistFilter) -> list[tuple[str, str]]:
        makes = filters.makes or [""]
        models = filters.models or [""]
        combos: list[tuple[str, str]] = []
        for make in makes:
            for model in models:
                if make and model:
                    combos.append((make, model))
                elif make:
                    combos.append((make, "all"))
        return combos or []

    @staticmethod
    def _build_search_url(
        make: str,
        model: str,
        year_min: int,
        year_max: int,
        page: int,
    ) -> str:
        params = [
            f"maker={quote(make.lower())}",
            f"model={quote(model.lower())}",
            f"year_s={year_min}",
            f"year_e={year_max}",
        ]
        if page > 1:
            params.append(f"page={page}")
        return f"{STOCK_SEARCH_URL}?{'&'.join(params)}"

    async def _parse_listing_text(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            return {}

        heuristic = self._heuristic_parse(text)
        if heuristic.get("title") and (heuristic.get("price_jpy") or heuristic.get("price_usd")):
            if not _JA_RE.search(text):
                if heuristic.get("price_jpy") and not heuristic.get("price_usd"):
                    heuristic["price_usd"] = await self.jpy_to_usd(float(heuristic["price_jpy"]))
                return heuristic

        if not os.getenv("ANTHROPIC_API_KEY"):
            logger.warning("ANTHROPIC_API_KEY missing — TCV heuristic parse only")
            return heuristic

        try:
            response = await self.client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": _LISTING_PARSE_PROMPT + text[:4000],
                    }
                ],
            )
            parsed = json.loads(response.content[0].text)
            if not isinstance(parsed, dict):
                return heuristic

            if parsed.get("price_jpy") and not parsed.get("price_usd"):
                parsed["price_usd"] = await self.jpy_to_usd(float(parsed["price_jpy"]))
            for key in ("year", "mileage_km"):
                if parsed.get(key) is not None:
                    parsed[key] = int(float(parsed[key]))
            return {**heuristic, **parsed}
        except json.JSONDecodeError as e:
            logger.warning("TCV Haiku JSON parse failed: %s", e)
        except Exception as e:
            logger.error("TCV Haiku listing parse failed: %s", e)
        return heuristic

    @staticmethod
    def _heuristic_parse(text: str) -> dict[str, Any]:
        result: dict[str, Any] = {"raw_text": text}

        text_norm = text.replace("\n", " ")
        stock_match = _STOCK_LINE_RE.search(text_norm)
        if not stock_match:
            stock_match = re.search(
                r"STOCK\s*(?P<year>19\d{2}|20\d{2})(?P<make>[A-Za-z-]+)\s+(?P<model>.+?)\s+FOB\s+(?P<price>.+)$",
                text_norm,
                re.IGNORECASE,
            )
        if stock_match:
            result["year"] = int(stock_match.group("year"))
            result["make"] = stock_match.group("make").strip()
            result["model"] = stock_match.group("model").strip()
            result["title"] = (
                f"{result['year']} {result['make']} {result['model']}".strip()
            )
            price_part = stock_match.group("price")
            usd = _USD_RE.search(price_part.replace(",", ""))
            jpy = _JPY_RE.search(price_part.replace(",", ""))
            if usd:
                result["price_usd"] = float(usd.group(1).replace(",", ""))
            if jpy:
                result["price_jpy"] = float(jpy.group(1).replace(",", ""))
        else:
            year_match = _YEAR_RE.search(text)
            if year_match:
                result["year"] = int(year_match.group(1))
            usd = _USD_RE.search(text.replace(",", ""))
            jpy = _JPY_RE.search(text.replace(",", ""))
            if usd:
                result["price_usd"] = float(usd.group(1).replace(",", ""))
            if jpy:
                result["price_jpy"] = float(jpy.group(1).replace(",", ""))
            result["title"] = text.split("FOB")[0].strip()[:250] or text[:250]

        km = _KM_RE.search(text.replace(",", ""))
        if km:
            result["mileage_km"] = int(km.group(1).replace(",", ""))

        chassis = _CHASSIS_RE.search(text.upper())
        if chassis:
            result["chassis_code"] = chassis.group(1)

        grade_match = re.search(r"(?:grade|評価|auction)\s*[:：]?\s*([1-5](?:\.\d)?|R|RA|RB)", text, re.I)
        if grade_match:
            result["auction_grade"] = grade_match.group(1)

        result.setdefault("location", "Japan")
        return result

    async def _extract_dom_listings(self, page: Page) -> list[dict]:
        try:
            rows = await page.evaluate(_EXTRACT_DOM_LISTINGS_JS)
            return rows or []
        except Exception as e:
            logger.error("TCV DOM extraction failed: %s", e)
            return []

    @staticmethod
    async def _launch() -> tuple[Any, Browser, Page]:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=pick_user_agent(),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9,ja;q=0.8"},
        )
        page = await context.new_page()
        return playwright, browser, page

    @staticmethod
    async def _close(playwright: Any, browser: Browser) -> None:
        try:
            await browser.close()
        except Exception as e:
            logger.debug("TCV browser close error: %s", e)
        finally:
            try:
                await playwright.stop()
            except Exception as e:
                logger.debug("TCV playwright stop error: %s", e)

    @staticmethod
    async def _navigate(page: Page, url: str) -> bool:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(1500)
            await random_delay()
            return True
        except Exception as e:
            logger.warning("TCV navigation failed for %s: %s", url, e)
            return False
