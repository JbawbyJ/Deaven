"""
backend/agents/scrapers/classic_com.py
CLASSIC.COM integration — sold comp data (ValuationAgent) and marketplace listings (ScoutAgent).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime
from typing import Any, Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from backend.agents.scrapers.ebay import extract_year_make_model
from shared.schemas.deal import ListingData, WatchlistFilter

logger = logging.getLogger(__name__)

BASE_SITE = "https://www.classic.com"
MODEL_PAGE_URL = f"{BASE_SITE}/m/{{make}}/{{model}}/"
MARKETPLACE_URL = f"{BASE_SITE}/cars-for-sale/"
MAX_PAGES = 10

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

_PRICE_RE = re.compile(r"[\$£€]?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?", re.IGNORECASE)
_MILEAGE_RE = re.compile(r"([\d,]+)\s*(?:mi|miles|km|kilometers)?", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


# ─── Shared utilities ─────────────────────────────────────────────────────────


async def random_delay(min_s: float = 1.5, max_s: float = 3.5) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


def pick_user_agent() -> str:
    return random.choice(USER_AGENTS)


def slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    match = _PRICE_RE.search(text.replace(",", ""))
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        amount *= 1_000
    elif suffix == "m":
        amount *= 1_000_000
    return amount


def _parse_mileage(text: str) -> Optional[int]:
    if not text:
        return None
    match = _MILEAGE_RE.search(text.replace(",", ""))
    if not match:
        return None
    return int(float(match.group(1).replace(",", "")))


def _parse_year(text: str) -> Optional[int]:
    if not text:
        return None
    match = _YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def _parse_sale_date(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


async def _launch_browser() -> tuple[Any, Browser, BrowserContext, Page]:
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent=pick_user_agent(),
        viewport={"width": 1440, "height": 900},
        locale="en-US",
    )
    page = await context.new_page()
    return playwright, browser, context, page


async def _close_browser(playwright: Any, browser: Browser) -> None:
    try:
        await browser.close()
    finally:
        await playwright.stop()


async def _navigate(page: Page, url: str) -> bool:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_function(
                """() => {
                    const title = document.title || '';
                    const body = document.body?.innerText || '';
                    return !title.includes('Just a moment')
                        && !body.includes('Performing security verification')
                        && body.length > 300;
                }""",
                timeout=45_000,
            )
        except Exception:
            logger.warning("CLASSIC.COM content wait timed out for %s", url)
        await random_delay()
        return True
    except Exception as e:
        logger.error("CLASSIC.COM navigation failed for %s: %s", url, e)
        return False


async def _go_next_page(page: Page) -> bool:
    selectors = [
        'a[rel="next"]:not([aria-disabled="true"])',
        'button[aria-label*="Next"]:not([disabled])',
        'a[aria-label*="Next"]:not([aria-disabled="true"])',
        '.pagination a.next:not(.disabled)',
        'a:has-text("Next"):not([aria-disabled="true"])',
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() == 0 or not await locator.is_visible():
                continue
            await locator.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30_000)
            await random_delay()
            return True
        except Exception:
            continue

    try:
        changed = await page.evaluate(
            """() => {
                const active = document.querySelector(
                    '.pagination .active, [aria-current="page"]'
                );
                if (!active) return false;
                const next = active.parentElement?.querySelector(
                    'a[href]:not(.active):not([aria-current="page"])'
                ) || active.nextElementSibling?.querySelector?.('a[href]')
                    || active.nextElementSibling;
                if (!next || !next.href) return false;
                next.click();
                return true;
            }"""
        )
        if changed:
            await page.wait_for_load_state("domcontentloaded", timeout=30_000)
            await random_delay()
            return True
    except Exception as e:
        logger.debug("CLASSIC.COM numeric pagination fallback failed: %s", e)

    return False


# ─── In-page extraction scripts ───────────────────────────────────────────────

_EXTRACT_SOLD_COMPS_JS = """
() => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const results = [];
  const seen = new Set();

  const push = (row) => {
    const key = [row.sale_price, row.sale_date, row.year, row.mileage, row.source_auction].join('|');
    if (!key || seen.has(key)) return;
    seen.add(key);
    results.push(row);
  };

  const headerMap = (headers) => ({
    price: headers.findIndex(h => /price|sold|sale|hammer|result/i.test(h)),
    date: headers.findIndex(h => /date|sold/i.test(h)),
    mileage: headers.findIndex(h => /mile|odometer|km/i.test(h)),
    year: headers.findIndex(h => /year/i.test(h)),
    condition: headers.findIndex(h => /condition|grade/i.test(h)),
    source: headers.findIndex(h => /source|auction|venue|platform/i.test(h)),
  });

  document.querySelectorAll('table').forEach((table) => {
    const headerCells = [...table.querySelectorAll('thead th, tr th')].map(th => norm(th.innerText).toLowerCase());
    if (!headerCells.length) return;
    const map = headerMap(headerCells);
    table.querySelectorAll('tbody tr').forEach((tr) => {
      const cells = [...tr.querySelectorAll('td')].map(td => norm(td.innerText));
      if (!cells.length) return;
      const get = (idx) => (idx >= 0 && cells[idx] ? cells[idx] : '');
      const yearText = get(map.year) || get(0);
      const priceText = get(map.price);
      if (!priceText && !yearText) return;
      push({
        sale_price: priceText,
        sale_date: get(map.date),
        mileage: get(map.mileage),
        year: yearText,
        condition: get(map.condition),
        source_auction: get(map.source),
      });
    });
  });

  document.querySelectorAll(
    '[class*="sale"], [class*="result"], [class*="auction"], article, li'
  ).forEach((node) => {
    const text = norm(node.innerText);
    if (!/\\$|£|€|sold|sale/i.test(text)) return;
    const priceEl = node.querySelector('[class*="price"], [class*="sold"], [class*="amount"]');
    const priceText = norm(priceEl?.innerText) || (text.match(/[$£€][\\d,]+(?:\\.\\d+)?[kKmM]?/) || [])[0] || '';
    if (!priceText) return;
    const yearMatch = text.match(/\\b(19\\d{2}|20\\d{2})\\b/);
    const mileageMatch = text.match(/([\\d,]+)\\s*(?:mi|miles|km)/i);
    const dateMatch = text.match(/\\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\\.?\\s+\\d{1,2},?\\s+\\d{4}\\b/i)
      || text.match(/\\b\\d{4}-\\d{2}-\\d{2}\\b/);
    const sourceEl = node.querySelector('a[href*="bringatrailer"], a[href*="carsandbids"], a[href*="auction"]');
    push({
      sale_price: priceText,
      sale_date: dateMatch ? dateMatch[0] : '',
      mileage: mileageMatch ? mileageMatch[0] : '',
      year: yearMatch ? yearMatch[0] : '',
      condition: (text.match(/\\b(?:#[1-4]|driver|excellent|good|fair|concours)\\b/i) || [])[0] || '',
      source_auction: norm(sourceEl?.innerText || sourceEl?.getAttribute('href') || ''),
    });
  });

  return results;
}
"""

_EXTRACT_MARKETPLACE_JS = """
() => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const listings = [];
  const seen = new Set();

  const cardSelector = [
    'article',
    '[class*="listing"]',
    '[class*="vehicle"]',
    '[class*="card"]',
    'li',
  ].join(',');

  const isListingHref = (href) => href && (
    href.includes('/listing/') ||
    href.includes('/car/') ||
    href.includes('/vehicle/') ||
    href.includes('/cars-for-sale/') && href.split('/').length > 4
  );

  document.querySelectorAll('a[href]').forEach((anchor) => {
    const href = anchor.href || '';
    if (!isListingHref(href) || seen.has(href)) return;

    const card = anchor.closest(cardSelector) || anchor.parentElement;
    if (!card) return;

    const text = norm(card.innerText);
    if (text.length < 8) return;

    const titleEl = card.querySelector('h1, h2, h3, h4, [class*="title"]');
    const title = norm(titleEl?.innerText || anchor.innerText);
    const priceText = norm(
      card.querySelector('[class*="price"], [class*="amount"]')?.innerText
      || (text.match(/[$£€][\\d,]+(?:\\.\\d+)?[kKmM]?/) || [])[0]
      || ''
    );
    if (!title || !priceText) return;

    const images = [...card.querySelectorAll('img[src]')]
      .map(img => img.src)
      .filter(Boolean);

    const location = norm(
      card.querySelector('[class*="location"], [class*="city"]')?.innerText
      || (text.match(/\\b[A-Z][a-z]+(?:,\\s+[A-Z]{2})?\\b/) || [])[0]
      || ''
    );

    const mileageMatch = text.match(/([\\d,]+)\\s*(?:mi|miles|km)/i);
    const yearMatch = title.match(/\\b(19\\d{2}|20\\d{2})\\b/) || text.match(/\\b(19\\d{2}|20\\d{2})\\b/);

    seen.add(href);
    listings.push({
      title,
      price: priceText,
      mileage: mileageMatch ? mileageMatch[0] : '',
      year: yearMatch ? yearMatch[0] : '',
      make: '',
      model: '',
      location,
      images,
      url: href,
    });
  });

  return listings;
}
"""


def _normalize_comp(raw: dict) -> Optional[dict]:
    year = raw.get("year")
    if isinstance(year, str):
        year = _parse_year(year)
    elif year is not None:
        year = int(year)

    price_text = str(raw.get("sale_price") or "")
    sale_price = _parse_price(price_text)
    if sale_price is None:
        return None

    mileage_text = str(raw.get("mileage") or "")
    mileage = _parse_mileage(mileage_text)

    sale_date = _parse_sale_date(str(raw.get("sale_date") or ""))

    return {
        "sale_price": sale_price,
        "sale_date": sale_date,
        "mileage": mileage,
        "year": year,
        "condition": str(raw.get("condition") or "").strip() or None,
        "source_auction": str(raw.get("source_auction") or "").strip() or None,
    }


def _normalize_listing(raw: dict) -> dict:
    title = str(raw.get("title") or "").strip()
    year = raw.get("year")
    if isinstance(year, str):
        year = _parse_year(year)
    elif year is not None:
        year = int(year)

    make = str(raw.get("make") or "").strip() or None
    model = str(raw.get("model") or "").strip() or None
    if title and (not year or not make or not model):
        parsed_year, parsed_make, parsed_model = extract_year_make_model(title)
        year = year or parsed_year
        make = make or parsed_make
        model = model or parsed_model

    price = _parse_price(str(raw.get("price") or ""))
    mileage_text = str(raw.get("mileage") or "")
    mileage = _parse_mileage(mileage_text)

    images = raw.get("images") or []
    if isinstance(images, str):
        images = [images]

    return {
        "title": title,
        "price": price,
        "mileage": mileage,
        "year": year,
        "make": make,
        "model": model,
        "location": str(raw.get("location") or "").strip() or None,
        "images": [str(u) for u in images if u],
        "url": str(raw.get("url") or "").strip(),
    }


def _in_year_range(year: Optional[int], year_min: int, year_max: int) -> bool:
    if year is None:
        return True
    return year_min <= year <= year_max


def _matches_watchlist(raw: dict, filters: WatchlistFilter) -> bool:
    make = (raw.get("make") or "").lower()
    model = (raw.get("model") or "").lower()
    title = (raw.get("title") or "").lower()

    if filters.makes:
        if not any(m.lower() in make or m.lower() in title for m in filters.makes):
            return False
    if filters.models:
        if not any(m.lower() in model or m.lower() in title for m in filters.models):
            return False
    if filters.price_min is not None and raw.get("price") is not None:
        if raw["price"] < filters.price_min:
            return False
    if filters.price_max is not None and raw.get("price") is not None:
        if raw["price"] > filters.price_max:
            return False
    if filters.year_min and raw.get("year"):
        if raw["year"] < filters.year_min:
            return False
    if filters.year_max and raw.get("year"):
        if raw["year"] > filters.year_max:
            return False
    return True


# ─── ROLE 1: Comp data ────────────────────────────────────────────────────────


class ClassicComCompClient:
    """Sold auction comps from CLASSIC.COM model market pages."""

    async def get_sold_comps(
        self,
        make: str,
        model: str,
        year_min: int,
        year_max: int,
    ) -> list[dict]:
        url = MODEL_PAGE_URL.format(make=slugify(make), model=slugify(model))
        all_comps: list[dict] = []
        seen: set[str] = set()

        playwright = None
        browser = None
        try:
            playwright, browser, _context, page = await _launch_browser()
            if not await _navigate(page, url):
                return []

            for page_num in range(1, MAX_PAGES + 1):
                raw_rows = await page.evaluate(_EXTRACT_SOLD_COMPS_JS)
                logger.debug(
                    "CLASSIC.COM comps page %d (%s): %d raw rows",
                    page_num,
                    url,
                    len(raw_rows),
                )

                for raw in raw_rows:
                    comp = _normalize_comp(raw)
                    if not comp:
                        continue
                    if not _in_year_range(comp.get("year"), year_min, year_max):
                        continue
                    key = "|".join(
                        str(comp.get(k))
                        for k in ("sale_price", "sale_date", "year", "mileage")
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    all_comps.append(comp)

                if page_num >= MAX_PAGES:
                    break
                if not await _go_next_page(page):
                    break

        except Exception as e:
            logger.error(
                "CLASSIC.COM comp scrape failed for %s %s: %s", make, model, e
            )
        finally:
            if playwright and browser:
                await _close_browser(playwright, browser)

        logger.info(
            "CLASSIC.COM comps: %d sold results for %s %s (%d-%d)",
            len(all_comps),
            make,
            model,
            year_min,
            year_max,
        )
        return all_comps


# ─── ROLE 2: Marketplace listings ─────────────────────────────────────────────


class ClassicComMarketplaceScraper:
    """Active for-sale listings from CLASSIC.COM marketplace."""

    async def fetch_listings(self, filters: WatchlistFilter) -> list[dict]:
        all_listings: list[dict] = []
        seen_urls: set[str] = set()

        playwright = None
        browser = None
        try:
            playwright, browser, _context, page = await _launch_browser()
            if not await _navigate(page, MARKETPLACE_URL):
                return []

            for page_num in range(1, MAX_PAGES + 1):
                raw_rows = await page.evaluate(_EXTRACT_MARKETPLACE_JS)
                logger.debug(
                    "CLASSIC.COM marketplace page %d: %d raw listings",
                    page_num,
                    len(raw_rows),
                )

                for raw in raw_rows:
                    listing = _normalize_listing(raw)
                    url = listing.get("url") or ""
                    if not url or url in seen_urls:
                        continue
                    if listing.get("price") is None or not listing.get("title"):
                        continue
                    if not _matches_watchlist(listing, filters):
                        continue
                    seen_urls.add(url)
                    all_listings.append(listing)

                if page_num >= MAX_PAGES:
                    break
                if not await _go_next_page(page):
                    break

        except Exception as e:
            logger.error("CLASSIC.COM marketplace scrape failed: %s", e)
        finally:
            if playwright and browser:
                await _close_browser(playwright, browser)

        logger.info("CLASSIC.COM marketplace: %d listings after filters", len(all_listings))
        return all_listings

    def parse_listing(self, raw: dict) -> Optional[ListingData]:
        try:
            listing = _normalize_listing(raw)
            title = listing.get("title") or ""
            price = listing.get("price")
            if not title or price is None or price <= 0:
                return None

            return ListingData(
                title=title,
                price=float(price),
                mileage=listing.get("mileage"),
                year=listing.get("year"),
                make=listing.get("make"),
                model=listing.get("model"),
                location=listing.get("location"),
                seller_type="private",
            )
        except Exception as e:
            logger.warning("Failed to parse CLASSIC.COM listing: %s", e)
            return None
