"""Offline listing adapters for Bring a Trailer, classic.com, eBay, and TCV.

Parsers read saved HTML. They do not fetch pages or read credentials.
Dedupe lives in backend.agents.ingestion.dedupe and groups listings with
shared.schemas.market.vehicle_key. The dedupe name is not imported here so
the submodule stays importable.
"""

from backend.agents.ingestion.bat import parse as parse_bat
from backend.agents.ingestion.classic_com import parse as parse_classic_com
from backend.agents.ingestion.ebay import parse as parse_ebay
from backend.agents.ingestion.extract import ParsedPage
from backend.agents.ingestion.tcv import parse as parse_tcv

__all__ = [
    "ParsedPage",
    "parse_bat",
    "parse_classic_com",
    "parse_ebay",
    "parse_tcv",
]
