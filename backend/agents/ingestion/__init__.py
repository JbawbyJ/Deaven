"""Offline listing adapters for Bring a Trailer, classic.com, eBay, and TCV.

HTML parsers read saved fixtures. They do not fetch pages or read credentials.
The only live-fetch policy is the official eBay Browse API adapter, unless a
licensed feed is configured through its env vars.
Dedupe lives in backend.agents.ingestion.dedupe and groups listings with
shared.schemas.market.vehicle_key. The dedupe name is not imported here so
the submodule stays importable.
"""

from backend.agents.ingestion.bat import parse as parse_bat
from backend.agents.ingestion.classic_com import parse as parse_classic_com
from backend.agents.ingestion.ebay import parse as parse_ebay
from backend.agents.ingestion.extract import ParsedPage
from backend.agents.ingestion.policy import SourcePolicy
from backend.agents.ingestion.tcv import parse as parse_tcv

__all__ = [
    "ParsedPage",
    "live_fetch_policies",
    "parse_bat",
    "parse_classic_com",
    "parse_ebay",
    "parse_tcv",
]


def live_fetch_policies() -> list[SourcePolicy]:
    """Policies allowed to read a source live. Parser-only sources stay off."""
    from backend.agents.ingestion.bat import POLICY as bat_policy
    from backend.agents.ingestion.classic_com import POLICY as classic_policy
    from backend.agents.ingestion.ebay import POLICY as ebay_html_policy
    from backend.agents.ingestion.ebay_browse import POLICY as browse_policy
    from backend.agents.ingestion.tcv import POLICY as tcv_policy

    from backend.agents.ingestion.licensed_feed import licensed_feed_policies

    catalog = (bat_policy, classic_policy, ebay_html_policy, tcv_policy, browse_policy)
    live = [policy for policy in catalog if policy.live_fetch_allowed]
    live.extend(licensed_feed_policies())
    return live
