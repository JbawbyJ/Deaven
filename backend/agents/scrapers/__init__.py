"""Source-specific listing scrapers."""

from backend.agents.scrapers.bat import BaTScraper
from backend.agents.scrapers.classic_com import (
    ClassicComCompClient,
    ClassicComMarketplaceScraper,
)
from backend.agents.scrapers.ebay import EbayMotorsScraper, extract_year_make_model
from backend.agents.scrapers.tcv import TCVScraper

__all__ = [
    "BaTScraper",
    "ClassicComCompClient",
    "ClassicComMarketplaceScraper",
    "EbayMotorsScraper",
    "TCVScraper",
    "extract_year_make_model",
]
