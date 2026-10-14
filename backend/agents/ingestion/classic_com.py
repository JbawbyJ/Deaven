"""classic.com recorded-HTML adapter. No live fetch and no credentials."""

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
    "classic.com's terms restrict scraping and automated access; the site also sits behind a bot check. "
    "This adapter parses saved listing HTML only, uses no credentials, and does not bypass that check. "
    "A live fetch has to be allowed by robots.txt for DeavenListingBot and then wait on this source's rate limiter. "
    "The shared Source catalog leaves robots_ok and tos_reviewed false; this note is not a live-crawl sign-off."
)

POLICY = SourcePolicy(
    code=DealSource.CLASSIC_COM,
    user_agent=USER_AGENT,
    min_interval_seconds=6.0,
    tos_note=TOS_NOTE,
)


def parse(html: str, *, fetched_at: datetime) -> ParsedPage:
    return parse_cards(
        html,
        fetched_at=fetched_at,
        code=POLICY.code,
        card_class="vehicle",
        title_class="vehicle-title",
        price_class="vehicle-price",
        base_url=POLICY.source.base_url,
        default_country="US",
        location_class="vehicle-location",
    )


def authorize(robots_txt: str, url: str, limiter: RateLimiter) -> None:
    authorize_policy(POLICY, robots_txt, url, limiter)


def limiter(**kwargs) -> RateLimiter:
    return RateLimiter(POLICY.min_interval_seconds, **kwargs)
