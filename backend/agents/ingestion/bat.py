"""Bring a Trailer recorded-HTML adapter. No live fetch and no credentials."""

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
    "Bring a Trailer's terms restrict automated collection and republication of auction content. "
    "This adapter parses saved listing HTML only. It does not log in and does not read credentials. "
    "A live fetch has to be allowed by robots.txt for DeavenListingBot and then wait on this source's rate limiter. "
    "The shared Source catalog leaves robots_ok and tos_reviewed false; this note is not a live-crawl sign-off."
)

POLICY = SourcePolicy(
    code=DealSource.BRING_A_TRAILER,
    user_agent=USER_AGENT,
    min_interval_seconds=8.0,
    tos_note=TOS_NOTE,
)


def parse(html: str, *, fetched_at: datetime) -> ParsedPage:
    return parse_cards(
        html,
        fetched_at=fetched_at,
        code=POLICY.code,
        card_class="listing",
        title_class="post-title",
        price_class="number",
        base_url=POLICY.source.base_url,
        default_country="US",
        map_class="listing-map",
    )


def authorize(robots_txt: str, url: str, limiter: RateLimiter) -> None:
    authorize_policy(POLICY, robots_txt, url, limiter)


def limiter(**kwargs) -> RateLimiter:
    return RateLimiter(POLICY.min_interval_seconds, **kwargs)
