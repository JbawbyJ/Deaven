"""
backend/agents/scrapers/bat.py
Bring a Trailer scraper — active auction listings (Scout) and sold comps (Valuation).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote_plus

from playwright.async_api import Browser, Page, async_playwright

from backend.agents.scrapers.ebay import extract_year_make_model
from shared.schemas.deal import ListingData, WatchlistFilter

logger = logging.getLogger(__name__)

AUCTIONS_URL = "https://bringatrailer.com/auctions/"
SEARCH_URL = "https://bringatrailer.com/search/"
MAX_PAGES = 5

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

_BID_PRICE_RE = re.compile(
    r"(?:Bid:|Sold for)\s*(?:USD\s*)?\$?\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_COUNTDOWN_RE = re.compile(r"(\d+):(\d{2}):(\d{2})\s*$")
_SOLD_DATE_RE = re.compile(r"on\s+(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)
_MILEAGE_RE = re.compile(r"([\d,]+)\s*(?:mi|miles)\b", re.IGNORECASE)
_WATCHERS_RE = re.compile(r"(\d[\d,]*)\s*(?:watchers|watching)", re.IGNORECASE)


async def random_delay(min_s: float = 2.0, max_s: float = 4.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


def pick_user_agent() -> str:
    return random.choice(USER_AGENTS)


def _slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    match = _BID_PRICE_RE.search(text.replace(",", ""))
    if not match:
        match = re.search(r"\$([\d,]+(?:\.\d+)?)", text.replace(",", ""))
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _parse_end_time(text: str) -> Optional[datetime]:
    if not text:
        return None
    match = _COUNTDOWN_RE.search(text.strip())
    if not match:
        return None
    hours, minutes, seconds = (int(match.group(i)) for i in range(1, 4))
    delta = timedelta(hours=hours, minutes=minutes, seconds=seconds)
    return datetime.now(timezone.utc) + delta


def _parse_sold_date(text: str) -> Optional[str]:
    if not text:
        return None
    match = _SOLD_DATE_RE.search(text)
    if match:
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_mileage(text: str) -> Optional[int]:
    if not text:
        return None
    match = _MILEAGE_RE.search(text.replace(",", ""))
    return int(match.group(1).replace(",", "")) if match else None


def _parse_watch_count(text: str) -> Optional[int]:
    if not text:
        return None
    match = _WATCHERS_RE.search(text)
    return int(match.group(1).replace(",", "")) if match else None


def _matches_watchlist(raw: dict, filters: WatchlistFilter) -> bool:
    title = str(raw.get("title") or "").lower()
    make = str(raw.get("make") or "").lower()
    model = str(raw.get("model") or "").lower()
    price = raw.get("current_bid")
    if isinstance(price, str):
        price = _parse_price(price)
    year = raw.get("year")

    if filters.makes and not any(m.lower() in make or m.lower() in title for m in filters.makes):
        return False
    if filters.models and not any(m.lower() in model or m.lower() in title for m in filters.models):
        return False
    if filters.price_min is not None and price is not None and price < filters.price_min:
        return False
    if filters.price_max is not None and price is not None and price > filters.price_max:
        return False
    if filters.year_min and year and year < filters.year_min:
        return False
    if filters.year_max and year and year > filters.year_max:
        return False
    return True


def _normalize_active_listing(raw: dict) -> dict:
    title = str(raw.get("title") or raw.get("name") or "").strip()
    bid_text = str(
        raw.get("current_bid")
        or raw.get("bid")
        or raw.get("high_bid")
        or raw.get("price")
        or raw.get("raw_text")
        or "",
    )
    url = str(raw.get("url") or raw.get("link") or raw.get("href") or "").strip()
    if url and not url.startswith("http"):
        url = f"https://bringatrailer.com{url}"

    if isinstance(raw.get("current_bid"), (int, float)):
        current_bid: Optional[float] = float(raw["current_bid"])
    else:
        current_bid = _parse_price(bid_text) if bid_text else None

    year, make, model = extract_year_make_model(title)
    year = raw.get("year") or year
    make = raw.get("make") or make
    model = raw.get("model") or model

    images = raw.get("images") or raw.get("image_urls") or []
    if isinstance(images, str):
        images = [images]
    if raw.get("thumbnail") or raw.get("thumbnailUrl"):
        thumb = raw.get("thumbnail") or raw.get("thumbnailUrl")
        if thumb not in images:
            images = [thumb, *images]

    end_time = raw.get("end_time") or raw.get("end_date") or raw.get("ends_at")
    if isinstance(end_time, str) and "Sold" not in end_time:
        parsed_end = _parse_end_time(end_time)
        if parsed_end:
            end_time = parsed_end
    elif end_time is None and bid_text and "Sold" not in bid_text:
        parsed_end = _parse_end_time(bid_text)
        if parsed_end:
            end_time = parsed_end

    return {
        "title": title,
        "current_bid": current_bid,
        "end_time": end_time,
        "watch_count": raw.get("watch_count") or _parse_watch_count(str(raw.get("raw_text") or "")),
        "images": [str(u) for u in images if u],
        "url": url,
        "location": raw.get("location") or raw.get("country"),
        "year": year,
        "make": make,
        "model": model,
        "mileage": raw.get("mileage"),
        "description": raw.get("description") or raw.get("excerpt"),
    }


def _normalize_sold_comp(raw: dict) -> Optional[dict]:
    title = str(raw.get("title") or "").strip()
    text = str(raw.get("raw_text") or raw.get("bid") or raw.get("current_bid") or "")
    price = _parse_price(text) or _parse_price(title)
    if not price:
        return None

    sold_date = _parse_sold_date(text) or _parse_sold_date(str(raw.get("sold_date") or ""))
    year, _, _ = extract_year_make_model(title)
    year = raw.get("year") or year

    url = str(raw.get("url") or raw.get("href") or "").strip()
    mileage = raw.get("mileage")
    if mileage is None:
        mileage = _parse_mileage(text)

    return {
        "price": price,
        "mileage": mileage,
        "year": year,
        "url": url,
        "sold_date": sold_date,
    }


def _within_days(sold_date: Optional[str], days: int) -> bool:
    if not sold_date or days <= 0:
        return True
    try:
        sold = datetime.fromisoformat(sold_date).date()
    except ValueError:
        return True
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    return sold >= cutoff


def _in_year_range(year: Optional[int], year_min: int, year_max: int) -> bool:
    if year is None:
        return True
    return year_min <= year <= year_max


def _title_matches_make_model(title: str, make: str, model: str) -> bool:
    t = title.lower()
    return make.lower() in t and model.lower() in t


_EXTRACT_NEXT_DATA_JS = """
() => {
  const el = document.getElementById('__NEXT_DATA__');
  if (!el) return null;
  try { return JSON.parse(el.textContent); } catch { return null; }
}
"""

_FIND_LISTINGS_IN_JSON_JS = """
(data) => {
  const results = [];
  const seen = new Set();

  const push = (item) => {
    if (!item || typeof item !== 'object') return;
    const title = item.title || item.name || item.post_title;
    const url = item.url || item.link || item.permalink;
    if (!title || !url) return;
    const key = String(url);
    if (seen.has(key)) return;
    seen.add(key);
    results.push(item);
  };

  const walk = (node, depth = 0) => {
    if (!node || depth > 10) return;
    if (Array.isArray(node)) {
      node.forEach((item) => {
        if (item && typeof item === 'object' && (item.title || item.name) && (item.url || item.link || item.slug)) {
          push(item);
        }
        walk(item, depth + 1);
      });
      return;
    }
    if (typeof node === 'object') {
      for (const key of ['listings', 'items', 'auctions', 'results', 'posts', 'data']) {
        if (Array.isArray(node[key])) walk(node[key], depth + 1);
      }
      Object.values(node).forEach((value) => walk(value, depth + 1));
    }
  };

  walk(data);
  return results;
}
"""

_EXTRACT_DOM_LISTINGS_JS = """
() => {
  const listings = [];
  const seen = new Set();

  document.querySelectorAll('a.listing-card').forEach((card) => {
    const url = card.href;
    if (!url || seen.has(url)) return;
    seen.add(url);

    const title = card.querySelector('h3')?.innerText?.trim() || '';
    const bidEl = card.querySelector('[class*="bid"]');
    const bidText = bidEl?.innerText?.replace(/\\s+/g, ' ').trim() || '';
    const img = card.querySelector('img')?.src || null;
    const location = card.querySelector('.show-country-name')?.innerText?.trim() || null;
    const text = card.innerText.replace(/\\s+/g, ' ').trim();

    listings.push({
      title,
      url,
      current_bid: bidText,
      end_time: bidText,
      watch_count: null,
      images: img ? [img] : [],
      location,
      raw_text: text,
    });
  });

  return listings;
}
"""


class BaTScraper:
    """Bring a Trailer — active listings and sold auction comps."""

    async def fetch_listings(self, filters: WatchlistFilter) -> list[dict]:
        all_listings: list[dict] = []
        seen_urls: set[str] = set()

        playwright = None
        browser = None
        try:
            playwright, browser, page = await self._launch()
            if not await self._navigate(page, AUCTIONS_URL):
                return []

            for page_num in range(1, MAX_PAGES + 1):
                url = AUCTIONS_URL if page_num == 1 else f"{AUCTIONS_URL}?page={page_num}"
                if page_num > 1:
                    if not await self._navigate(page, url):
                        break

                batch = await self._extract_listings(page)
                if not batch:
                    if page_num == 1:
                        logger.warning("BaT: no listings extracted from auctions page")
                    break

                new_count = 0
                for raw in batch:
                    listing = _normalize_active_listing(raw)
                    listing_url = listing.get("url") or ""
                    if not listing_url or listing_url in seen_urls:
                        continue
                    if not _matches_watchlist(listing, filters):
                        continue
                    seen_urls.add(listing_url)
                    all_listings.append(listing)
                    new_count += 1

                logger.debug("BaT auctions page %d: %d new listings", page_num, new_count)
                if new_count == 0 and page_num > 1:
                    break
                if page_num < MAX_PAGES:
                    await random_delay()

        except Exception as e:
            logger.error("BaT fetch_listings failed: %s", e)
        finally:
            if playwright and browser:
                await self._close(playwright, browser)

        logger.info("BaT: fetched %d active listings", len(all_listings))
        return all_listings

    def parse_listing(self, raw: dict) -> Optional[ListingData]:
        try:
            listing = _normalize_active_listing(raw)
            title = listing.get("title") or ""
            price = listing.get("current_bid")
            if isinstance(price, str):
                price = _parse_price(price)
            if not title or price is None or price <= 0:
                return None

            end_date = listing.get("end_time")
            if isinstance(end_date, str):
                try:
                    end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except ValueError:
                    parsed = _parse_end_time(end_date)
                    end_date = parsed

            return ListingData(
                title=title,
                price=float(price),
                mileage=listing.get("mileage"),
                year=listing.get("year"),
                make=listing.get("make"),
                model=listing.get("model"),
                location=listing.get("location"),
                description=listing.get("description"),
                seller_type="private",
                end_date=end_date,
                watch_count=listing.get("watch_count"),
            )
        except Exception as e:
            logger.warning("Failed to parse BaT listing: %s", e)
            return None

    async def get_sold_comps(
        self,
        make: str,
        model: str,
        year_min: int,
        year_max: int,
        days: int = 90,
    ) -> list[dict]:
        """
        Sold auction comps for MarketCompAggregator.
        Returns dicts with keys: price, mileage, year, url, sold_date.
        """
        query = quote_plus(f"{make} {model}")
        search_url = f"{SEARCH_URL}?q={query}&sold=1"
        fallback_url = f"https://bringatrailer.com/{_slugify(make)}/{_slugify(model)}/"

        comps: list[dict] = []
        seen: set[str] = set()

        playwright = None
        browser = None
        try:
            playwright, browser, page = await self._launch()

            for base_url in (search_url, fallback_url):
                if not await self._navigate(page, base_url):
                    continue

                batch = await self._extract_listings(page, sold_only=True)
                if batch:
                    logger.debug("BaT sold comps: %d raw rows from %s", len(batch), page.url)
                    break
            else:
                logger.warning("BaT sold comp search returned no results for %s %s", make, model)
                return []

            for raw in batch:
                title = str(raw.get("title") or "")
                if not _title_matches_make_model(title, make, model):
                    continue

                comp = _normalize_sold_comp(raw)
                if not comp:
                    continue
                if not _in_year_range(comp.get("year"), year_min, year_max):
                    continue
                if not _within_days(comp.get("sold_date"), days):
                    continue

                key = "|".join(str(comp.get(k)) for k in ("price", "sold_date", "year", "url"))
                if key in seen:
                    continue
                seen.add(key)
                comps.append(comp)

        except Exception as e:
            logger.error("BaT get_sold_comps failed for %s %s: %s", make, model, e)
        finally:
            if playwright and browser:
                await self._close(playwright, browser)

        logger.info(
            "BaT sold comps: %d results for %s %s (%d-%d, %dd)",
            len(comps),
            make,
            model,
            year_min,
            year_max,
            days,
        )
        return comps

    async def _extract_listings(self, page: Page, sold_only: bool = False) -> list[dict]:
        next_data = await page.evaluate(_EXTRACT_NEXT_DATA_JS)
        if next_data:
            try:
                found = await page.evaluate(_FIND_LISTINGS_IN_JSON_JS, next_data)
                if found:
                    logger.debug("BaT: extracted %d listings from __NEXT_DATA__", len(found))
                    if sold_only:
                        found = [
                            item
                            for item in found
                            if "sold" in json.dumps(item).lower()
                        ]
                    return found
            except Exception as e:
                logger.debug("BaT __NEXT_DATA__ parse failed: %s", e)

        for script in ('script[type="application/json"]', 'script[id="__NEXT_DATA__"]'):
            try:
                payload = await page.evaluate(
                    """
                    (selector) => {
                      const nodes = document.querySelectorAll(selector);
                      for (const node of nodes) {
                        try {
                          const parsed = JSON.parse(node.textContent || '');
                          if (parsed) return parsed;
                        } catch {}
                      }
                      return null;
                    }
                    """,
                    script,
                )
                if payload:
                    found = await page.evaluate(_FIND_LISTINGS_IN_JSON_JS, payload)
                    if found:
                        logger.debug("BaT: extracted %d listings from JSON script tag", len(found))
                        return found
            except Exception:
                continue

        dom_rows = await page.evaluate(_EXTRACT_DOM_LISTINGS_JS)
        if sold_only:
            dom_rows = [
                row
                for row in dom_rows
                if "sold for" in str(row.get("raw_text") or "").lower()
            ]
        else:
            dom_rows = [
                row
                for row in dom_rows
                if "sold for" not in str(row.get("raw_text") or "").lower()
            ]
        if dom_rows:
            logger.debug("BaT: extracted %d listings from DOM", len(dom_rows))
        return dom_rows or []

    @staticmethod
    async def _launch() -> tuple[Any, Browser, Page]:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=pick_user_agent(),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()
        return playwright, browser, page

    @staticmethod
    async def _close(playwright: Any, browser: Browser) -> None:
        try:
            await browser.close()
        except Exception as e:
            logger.debug("BaT browser close error: %s", e)
        finally:
            try:
                await playwright.stop()
            except Exception as e:
                logger.debug("BaT playwright stop error: %s", e)

    @staticmethod
    async def _navigate(page: Page, url: str) -> bool:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_selector("a.listing-card, a[href*='/listing/']", timeout=20_000)
            await random_delay()
            return True
        except Exception as e:
            logger.warning("BaT navigation issue for %s: %s", url, e)
            return False
