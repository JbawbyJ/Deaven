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

TOS_URL = "https://www.tc-v.com/about/termsofuse/"
TOS_NOTE = (
    "Verdict: gathering Service information by a method other than TCV's is barred, including for commercial use. "
    "Parser-only. Status: pending RJ decision. "
    f"Terms: {TOS_URL} "
    "Clause (Article 11.1.11): \"using, gathering, or processing the information provided in the Service "
    "by a method other than the method provided by TCV, whether legal or illegal, and whether or not it "
    "infringes upon rights, or using the Service by a method other than the method provided by TCV, for "
    "profit or for commercial purposes.\" "
    "tc-v.com HTML is parsed from saved fixtures only. This adapter uses no credentials and does not call an FX or Anthropic API. "
    "The asking price stays in the currency printed on the page, so JPY is not converted. "
    "Kilometer odometers are stored as miles on the listing; the raw kilometer figure stays in provenance. "
    "It is not on the live fetch list."
)

POLICY = SourcePolicy(
    code=DealSource.TCV,
    user_agent=USER_AGENT,
    min_interval_seconds=5.0,
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
