"""
backend/agents/scout.py
Scout Agent — crawls configured sources, ingests listings, deduplicates.
Returns a list of new DealPayloads ready for the orchestrator pipeline.
"""

from __future__ import annotations
import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Optional

from backend.agents.scrapers.tcv import TCVScraper
from backend.agents.scrapers.bat import BaTScraper
from backend.agents.scrapers.ebay import EbayMotorsScraper
from backend.agents.scrapers.classic_com import ClassicComMarketplaceScraper

import httpx

from shared.schemas.deal import (
    DealPayload, DealSource, DealStatus, ListingData, WatchlistFilter
)

logger = logging.getLogger(__name__)


# ─── Source Scrapers ──────────────────────────────────────────────────────────

class EbayMotorsScraper:
    """eBay Motors — Buy It Now and auction listings."""

    SEARCH_URL = "https://www.ebay.com/sch/i.html"

    async def fetch_listings(self, filters: WatchlistFilter) -> list[dict]:
        query = " ".join(filters.makes + filters.models)
        params = {
            "_nkw":    query,
            "_sacat":  "6001",   # eBay Motors category
            "LH_Sold": "0",
            "_sop":    "10",     # sort by newly listed
        }

        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.get(self.SEARCH_URL, params=params)
                resp.raise_for_status()
                # TODO: parse HTML with BeautifulSoup
                # Returning stub for now
                return []
            except Exception as e:
                logger.error(f"eBay fetch failed: {e}")
                return []


class FacebookMarketplaceScraper:
    """
    Facebook Marketplace — requires authenticated session.
    Use Apify's Facebook Marketplace scraper actor in production.
    """

    APIFY_ACTOR_URL = "https://api.apify.com/v2/acts/apify~facebook-marketplace-scraper/runs"

    async def fetch_listings(self, filters: WatchlistFilter, apify_token: str) -> list[dict]:
        payload = {
            "searchQuery": " ".join(filters.makes + filters.models),
            "maxItems":    50,
            "minPrice":    filters.price_min,
            "maxPrice":    filters.price_max,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(
                    self.APIFY_ACTOR_URL,
                    json=payload,
                    params={"token": apify_token}
                )
                resp.raise_for_status()
                run_id = resp.json()["data"]["id"]
                # Poll for results
                return await self._poll_results(client, run_id, apify_token)
            except Exception as e:
                logger.error(f"Facebook Marketplace fetch failed: {e}")
                return []

    async def _poll_results(self, client, run_id: str, token: str) -> list[dict]:
        dataset_url = f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items"
        for _ in range(12):   # poll up to 2 minutes
            await asyncio.sleep(10)
            resp = await client.get(dataset_url, params={"token": token})
            if resp.status_code == 200:
                return resp.json()
        return []


# ─── Deduplication ────────────────────────────────────────────────────────────

class DeduplicationStore:
    """
    Tracks seen listing fingerprints to avoid re-processing.
    In production: backed by Supabase table or Redis.
    """

    def __init__(self):
        self._seen: set[str] = set()   # in-memory for now

    def fingerprint(self, url: str, price: float) -> str:
        return hashlib.md5(f"{url}:{price}".encode()).hexdigest()

    def is_seen(self, url: str, price: float) -> bool:
        fp = self.fingerprint(url, price)
        return fp in self._seen

    def mark_seen(self, url: str, price: float):
        self._seen.add(self.fingerprint(url, price))

    async def load_from_db(self, db_client):
        """Load seen fingerprints from Supabase on startup."""
        rows = await db_client.table("deal_fingerprints").select("fingerprint").execute()
        self._seen = {r["fingerprint"] for r in rows.data}

    async def persist_to_db(self, fingerprint: str, db_client):
        await db_client.table("deal_fingerprints").insert(
            {"fingerprint": fingerprint, "seen_at": datetime.utcnow().isoformat()}
        ).execute()


# ─── Scout Agent ──────────────────────────────────────────────────────────────

class ScoutAgent:
    """
    Main Scout Agent.
    Coordinates all source scrapers, deduplicates, and returns
    fresh DealPayloads ready for the orchestrator pipeline.
    """

   
    SOURCE_MAP = {
        DealSource.BRING_A_TRAILER: BaTScraper,
        DealSource.EBAY:            EbayMotorsScraper,
        DealSource.CLASSIC_COM:     ClassicComMarketplaceScraper,
        DealSource.TCV:             TCVScraper,
    }

    def __init__(self, dedup_store: Optional[DeduplicationStore] = None):
        self.dedup = dedup_store or DeduplicationStore()

    async def run(
        self,
        filters: WatchlistFilter,
        sources: Optional[list[DealSource]] = None,
    ) -> list[DealPayload]:
        """
        Main entry point. Crawls all configured sources for a given filter.
        Returns new, deduplicated DealPayloads.
        """
        target_sources = sources or filters.sources or list(self.SOURCE_MAP.keys())
        tasks = [
            self._fetch_source(source, filters)
            for source in target_sources
            if source in self.SOURCE_MAP
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        payloads = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Source fetch error: {result}")
                continue
            payloads.extend(result)

        logger.info(f"Scout: {len(payloads)} new listings found across {len(target_sources)} sources")
        return payloads

    async def _fetch_source(
        self,
        source: DealSource,
        filters: WatchlistFilter,
    ) -> list[DealPayload]:
        scraper_cls = self.SOURCE_MAP[source]
        scraper     = scraper_cls()
        raw_listings = await scraper.fetch_listings(filters)

        payloads = []
        for raw in raw_listings:
            listing = scraper.parse_listing(raw) if hasattr(scraper, "parse_listing") else None
            if not listing:
                continue

            url = raw.get("url", raw.get("link", ""))
            if not url:
                continue

            # Skip if already seen at this price
            if self.dedup.is_seen(url, listing.price):
                continue

            # Apply pre-filter
            if not self._matches_filter(listing, filters):
                continue

            self.dedup.mark_seen(url, listing.price)

            payload = DealPayload(
                source   = source,
                url      = url,
                listing  = listing,
                images   = raw.get("images", []),
                status   = DealStatus.INGESTED,
            )
            payloads.append(payload)

        return payloads

    def _matches_filter(self, listing: ListingData, f: WatchlistFilter) -> bool:
        """Quick pre-filter before spinning up expensive agents."""
        if f.makes and listing.make and listing.make.lower() not in [m.lower() for m in f.makes]:
            return False
        if f.models and listing.model and listing.model.lower() not in [m.lower() for m in f.models]:
            return False
        if f.price_min and listing.price < f.price_min:
            return False
        if f.price_max and listing.price > f.price_max:
            return False
        if f.mileage_max and listing.mileage and listing.mileage > f.mileage_max:
            return False
        if f.year_min and listing.year and listing.year < f.year_min:
            return False
        if f.year_max and listing.year and listing.year > f.year_max:
            return False
        return True


# ─── Manual Ingest ────────────────────────────────────────────────────────────

async def ingest_url(url: str) -> DealPayload:
    """
    Manual trigger — user pastes a URL into dashboard.
    Detects source, scrapes listing, returns initialized payload.
    """
    source = _detect_source(url)
    # TODO: dispatch to correct scraper based on source
    # For now return a stub payload
    return DealPayload(
        source  = source,
        url     = url,
        listing = ListingData(title="Manual ingest pending", price=0),
        status  = DealStatus.INGESTED,
    )

def _detect_source(url: str) -> DealSource:
    if "bringatrailer" in url:   return DealSource.BRING_A_TRAILER
    if "carsandbids"   in url:   return DealSource.CARS_AND_BIDS
    if "ebay"          in url:   return DealSource.EBAY
    if "facebook"      in url:   return DealSource.FACEBOOK
    if "autotrader"    in url:   return DealSource.AUTOTRADER
    if "hemmings"      in url:   return DealSource.HEMMINGS
    if "craigslist"    in url:   return DealSource.CRAIGSLIST
    return DealSource.MANUAL
