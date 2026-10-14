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

TOS_URL = "https://bringatrailer.com/terms-of-use/"
TOS_NOTE = (
    "Verdict: scraping and automated access are barred. Parser-only. Status: pending RJ decision. "
    f"Terms: {TOS_URL} "
    "Clause: \"You may also not use any software robots, spider, crawlers, or other data gathering "
    "or extraction tools, whether automated or manual, to access, acquire, copy, monitor, scrape or "
    "aggregate the BaT Services, Content or any portion thereof.\" "
    "Bring a Trailer HTML is parsed from saved fixtures only. This adapter does not log in and does not read credentials. "
    "It is not on the live fetch list."
)

POLICY = SourcePolicy(
    code=DealSource.BRING_A_TRAILER,
    user_agent=USER_AGENT,
    min_interval_seconds=8.0,
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
