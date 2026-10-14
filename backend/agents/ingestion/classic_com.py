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

TOS_URL = "https://www.classic.com/about/terms-conditions/"
TOS_NOTE = (
    "Verdict: scraping and automated access are barred without prior written consent. Parser-only. "
    "Status: pending RJ decision. "
    f"Terms: {TOS_URL} "
    "Clause: \"Use any robot, spider, site search/retrieval application or other manual or automatic "
    "devices to retrieve, index, “scrape,” “data mine” or otherwise gather any Content, or reproduce "
    "or circumvent the navigational structure or presentation of the Services, without CLASSIC.COM’s "
    "express prior written consent.\" "
    "classic.com HTML is parsed from saved fixtures only. This adapter uses no credentials and does not bypass the bot check. "
    "It is not on the live fetch list."
)

POLICY = SourcePolicy(
    code=DealSource.CLASSIC_COM,
    user_agent=USER_AGENT,
    min_interval_seconds=6.0,
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
