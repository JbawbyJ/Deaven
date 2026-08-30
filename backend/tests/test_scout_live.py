from __future__ import annotations

import asyncio

from backend.agents.scrapers.ebay import finding_keywords
from backend.agents.scout import ScoutAgent
from shared.schemas.deal import DealSource, ListingData, WatchlistFilter


def test_finding_keywords_e46_hunt():
    hunt = WatchlistFilter(
        name="E46 M3 Hunt",
        makes=["BMW"],
        models=["M3"],
        year_min=2001,
        year_max=2006,
    )
    keywords = finding_keywords(hunt)
    assert "E46" in keywords
    assert "BMW" in keywords
    assert "M3" in keywords
    assert "2001" not in keywords


def test_finding_keywords_non_e46_keeps_years():
    keywords = finding_keywords(
        WatchlistFilter(name="FD", makes=["Mazda"], models=["RX-7"], year_min=1992, year_max=1995)
    )
    assert "E46" not in keywords
    assert "1992" in keywords


class _Boom:
    async def fetch_listings(self, filters):
        raise RuntimeError("bat down")


class _Ok:
    def __init__(self, source: DealSource) -> None:
        self.source = source

    async def fetch_listings(self, filters):
        return [{"url": f"https://example.com/{self.source.value}/e46", "images": ["x.jpg"]}]

    def parse_listing(self, raw):
        return ListingData(
            title="2003 BMW M3 Coupe",
            price=28900,
            year=2003,
            make="BMW",
            model="M3",
        )


def test_live_scout_isolates_bat_classic_tcv_failures(monkeypatch):
    monkeypatch.setenv("SCOUT_BACKEND", "live")

    def fake_scraper(self, source: DealSource):
        if source == DealSource.BRING_A_TRAILER:
            return _Boom()
        if source == DealSource.CLASSIC_COM:
            raise RuntimeError("classic import failed")
        return _Ok(source)

    monkeypatch.setattr(ScoutAgent, "_scraper_for", fake_scraper)
    agent = ScoutAgent()
    hunt = WatchlistFilter(
        name="E46 M3 Hunt",
        makes=["BMW"],
        models=["M3"],
        year_min=2001,
        year_max=2006,
    )
    payloads = asyncio.run(agent.run(hunt))
    sources = {p.source for p in payloads}
    assert DealSource.EBAY in sources or DealSource.TCV in sources
    assert DealSource.BRING_A_TRAILER not in sources
    assert DealSource.CLASSIC_COM not in sources
    assert payloads
