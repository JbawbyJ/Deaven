"""eBay recorded-HTML parser. Scraping is barred, so this path is fixtures only.

Live reads go through backend.agents.ingestion.ebay_browse (the Browse API).
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

TOS_URL = "https://www.ebay.com.au/help/policies/member-behaviour-policies/user-agreement?id=4259"
TOS_NOTE = (
    "Verdict: the User Agreement bars scraping. HTML is parser-only. Status: pending RJ decision "
    "for any HTML crawl. Live reads use the official Browse API instead. "
    f"Terms: {TOS_URL} "
    "(same agreement id 4259; the US help URL returned 403 when this clause was checked). "
    "Section 15: \"You agree that you will not use any robot, spider, scraper or other automated means "
    "to access the eBay services for any purpose without our express written permission.\" "
    "This HTML parser reads saved fixtures only. It does not call the Finding API and does not read "
    "EBAY_APP_ID, EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, or any other credential. "
    "It is not on the live fetch list."
)

POLICY = SourcePolicy(
    code=DealSource.EBAY,
    user_agent=USER_AGENT,
    min_interval_seconds=3.0,
    tos_note=TOS_NOTE,
    tos_url=TOS_URL,
    live_fetch_allowed=False,
    review_status="pending RJ decision",
)
LIVE_FETCH_ALLOWED = POLICY.live_fetch_allowed


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
