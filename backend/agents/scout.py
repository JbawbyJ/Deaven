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

import httpx

from backend.core.settings import scout_backend
from shared.schemas.deal import (
    DealPayload, DealSource, DealStatus, ListingData, WatchlistFilter
)

logger = logging.getLogger(__name__)


# ─── Source Scrapers ──────────────────────────────────────────────────────────

class LocalCatalogScraper:
    """
    In-repo catalog used when SCOUT_BACKEND=local.
    Same fetch_listings / parse_listing surface as live scrapers.
    """

    async def fetch_listings(self, filters: WatchlistFilter) -> list[dict]:
        from backend.data.catalog import CATALOG, match_filters

        return [item for item in CATALOG if match_filters(item, filters)]

    def parse_listing(self, raw: dict) -> Optional[ListingData]:
        from backend.agents.local_pipeline import listing_from_catalog

        try:
            return listing_from_catalog(raw)
        except Exception as exc:
            logger.warning("Catalog parse failed: %s", exc)
            return None


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

def select_sources(
    filters: WatchlistFilter,
    sources: Optional[list[DealSource]] = None,
) -> list[DealSource]:
    """
    Resolve which live scrapers to run.

    Empty sources (live mode) must not silently skip — fall back to SOURCE_MAP.
    If sources are set, intersect with keys we actually know how to crawl.
    Local catalog mode ignores this list and still uses CATALOG.
    """
    available = list(ScoutAgent.SOURCE_MAP.keys())
    requested = list(sources) if sources else list(filters.sources or [])
    if not requested:
        return available
    allowed = set(available)
    return [source for source in requested if source in allowed]


class ScoutAgent:
    """
    Main Scout Agent.
    Coordinates all source scrapers, deduplicates, and returns
    fresh DealPayloads ready for the orchestrator pipeline.
    """

   
    SOURCE_MAP = {
        DealSource.BRING_A_TRAILER: "bat",
        DealSource.EBAY:            "ebay",
        DealSource.CLASSIC_COM:     "classic_com",
        DealSource.TCV:             "tcv",
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
        if scout_backend() == "local":
            from backend.agents.local_pipeline import scout_catalog

            payloads = scout_catalog(filters)
            logger.info("Scout (local catalog): %d listings", len(payloads))
            return payloads

        target_sources = select_sources(filters, sources)
        if not target_sources:
            logger.warning("Scout: no crawlable sources selected for filter '%s'", filters.name)
            return []

        tasks = [
            self._fetch_source(source, filters)
            for source in target_sources
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

    def _scraper_for(self, source: DealSource):
        if scout_backend() == "local":
            return LocalCatalogScraper()

        key = self.SOURCE_MAP[source]
        if key == "bat":
            from backend.agents.scrapers.bat import BaTScraper

            return BaTScraper()
        if key == "ebay":
            from backend.agents.scrapers.ebay import EbayMotorsScraper

            return EbayMotorsScraper()
        if key == "classic_com":
            from backend.agents.scrapers.classic_com import ClassicComMarketplaceScraper

            return ClassicComMarketplaceScraper()
        if key == "tcv":
            from backend.agents.scrapers.tcv import TCVScraper

            return TCVScraper()
        raise KeyError(source)

    async def _fetch_source(
        self,
        source: DealSource,
        filters: WatchlistFilter,
    ) -> list[DealPayload]:
        try:
            scraper = self._scraper_for(source)
            raw_listings = await scraper.fetch_listings(filters)
        except Exception as exc:
            logger.error("Source %s failed: %s", source, exc)
            return []

        payloads = []
        for raw in raw_listings:
            listing = scraper.parse_listing(raw) if hasattr(scraper, "parse_listing") else None
            if not listing:
                continue

            url = raw.get("url") or raw.get("link") or ""
            if hasattr(scraper, "extract_url"):
                url = scraper.extract_url(raw) or url
            if not url:
                continue
            images = raw.get("images") or []
            if hasattr(scraper, "extract_images"):
                extracted = scraper.extract_images(raw)
                if extracted:
                    images = extracted

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
                images   = images,
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
    Manual trigger — user pastes a URL into the dashboard.
    Local mode resolves catalog slugs / demo URLs. Live scrapers can
    replace this without changing the API contract.
    """
    from backend.agents.local_pipeline import ingest_url as local_ingest
    from backend.core.settings import pipeline_mode

    if pipeline_mode() == "local" or scout_backend() == "local":
        return local_ingest(url)

    from backend.agents.local_pipeline import payload_from_url

    return payload_from_url(url)

def _detect_source(url: str) -> DealSource:
    from backend.agents.local_pipeline import detect_source

    return detect_source(url)
