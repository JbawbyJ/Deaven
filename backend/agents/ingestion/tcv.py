"""TCV (tc-v.com) recorded-HTML adapter. No FX call and no credentials.

Asking prices stay in the currency printed on the page. Kilometer odometers
are stored as miles so vehicle_key's mile bands line up; the kilometer figure
stays on the provenance payload.
"""

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
    "tc-v.com's terms restrict automated collection of export stock. "
    "This adapter parses saved HTML only, uses no credentials, and does not call an FX or Anthropic API. "
    "The asking price stays in the currency printed on the page, so JPY is not converted. "
    "Kilometer odometers are stored as miles on the listing; the raw kilometer figure stays in provenance. "
    "A live fetch has to be allowed by robots.txt for DeavenListingBot and then wait on this source's rate limiter. "
    "The shared Source catalog leaves robots_ok and tos_reviewed false; this note is not a live-crawl sign-off."
)

POLICY = SourcePolicy(
    code=DealSource.TCV,
    user_agent=USER_AGENT,
    min_interval_seconds=5.0,
    tos_note=TOS_NOTE,
)


def parse(html: str, *, fetched_at: datetime) -> ParsedPage:
    return parse_cards(
        html,
        fetched_at=fetched_at,
        code=POLICY.code,
        card_class="stock-item",
        title_class="stock-title",
        price_class="stock-price",
        base_url=POLICY.source.base_url,
        default_country="JP",
        location_class="stock-location",
        mileage_unit="km",
    )


def authorize(robots_txt: str, url: str, limiter: RateLimiter) -> None:
    authorize_policy(POLICY, robots_txt, url, limiter)


def limiter(**kwargs) -> RateLimiter:
    return RateLimiter(POLICY.min_interval_seconds, **kwargs)
