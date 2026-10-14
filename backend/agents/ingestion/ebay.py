"""eBay recorded-HTML adapter. No Finding API call and no EBAY_APP_ID."""

from __future__ import annotations

from datetime import datetime

from shared.schemas.deal import DealSource

from backend.agents.ingestion.extract import ParsedPage, parse_cards
from backend.agents.ingestion.policy import (
    USER_AGENT,
    RateLimiter,
    SourcePolicy,
    authorize as authorize_policy,
)

TOS_NOTE = (
    "eBay's User Agreement and robots.txt limit automated access. "
    "This adapter does not call the Finding API and does not read EBAY_APP_ID or any other credential. "
    "It parses saved listing HTML only. A live fetch has to be allowed by robots.txt for DeavenListingBot "
    "and then wait on this source's rate limiter. "
    "The shared Source catalog leaves robots_ok and tos_reviewed false; this note is not a live-crawl sign-off."
)

POLICY = SourcePolicy(
    code=DealSource.EBAY,
    user_agent=USER_AGENT,
    min_interval_seconds=3.0,
    tos_note=TOS_NOTE,
)


def parse(html: str, *, fetched_at: datetime) -> ParsedPage:
    return parse_cards(
        html,
        fetched_at=fetched_at,
        code=POLICY.code,
        card_class="x-item",
        title_class="x-item-title__mainTitle",
        price_class="x-price-primary",
        base_url=POLICY.source.base_url,
        default_country="US",
        location_class="item-location",
        map_class="item-map",
    )


def authorize(robots_txt: str, url: str, limiter: RateLimiter) -> None:
    authorize_policy(POLICY, robots_txt, url, limiter)


def limiter(**kwargs) -> RateLimiter:
    return RateLimiter(POLICY.min_interval_seconds, **kwargs)
