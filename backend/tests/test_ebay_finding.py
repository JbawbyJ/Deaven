"""eBay Finding adapter. Fixture responses only — no live network."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from backend.ingestion.ebay_finding import EbayFindingAdapter, EbayFindingError, MissingAppId
from backend.ingestion.http import USER_AGENT, RobotsDisallowed

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingestion"
FINDING = json.loads((FIXTURES / "finding_items.json").read_text())
ALLOW = (FIXTURES / "robots_allow.txt").read_text()
DISALLOW = (FIXTURES / "robots_disallow.txt").read_text()


class Ticker:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class Web:
    def __init__(self, robots: str, api_status: int = 200, api_body: str | None = None) -> None:
        self.robots = robots
        self.api_status = api_status
        self.api_body = api_body if api_body is not None else json.dumps(FINDING)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
        self.calls.append((url, headers))
        if url.endswith("/robots.txt"):
            return 200, self.robots
        return self.api_status, self.api_body


def _adapter(web: Web, **kwargs) -> tuple[EbayFindingAdapter, Ticker]:
    ticker = Ticker()
    adapter = EbayFindingAdapter(
        app_id="test-app-id",
        transport=web,
        min_interval_s=0,
        clock=ticker.clock,
        sleep=ticker.sleep,
        **kwargs,
    )
    return adapter, ticker


def test_fetch_maps_fixture_items_and_identifies_the_app(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("live network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    web = Web(ALLOW)
    adapter, ticker = _adapter(web)
    listings = adapter.fetch("BMW M3", price_min=1000)

    assert ticker.sleeps == [5.0]
    assert [url for url, _headers in web.calls][0].endswith("/robots.txt")
    api_url, api_headers = web.calls[1]
    assert "FindingService" in api_url
    assert "SECURITY-APPNAME=test-app-id" in api_url
    assert "MinPrice" in api_url
    assert api_headers["User-Agent"] == USER_AGENT
    assert "Deaven" in USER_AGENT

    by_id = {item.listing_id: item for item in listings}
    assert set(by_id) == {"ebay:111", "ebay:222", "ebay:333"}

    austin = by_id["ebay:111"]
    assert austin.vin == "1HGCM82633A004352"
    assert austin.year == 2003 and austin.make == "BMW" and austin.model == "M3"
    assert austin.trim == "Coupe"
    assert austin.trim_normalized == "coupe"
    assert austin.mileage == 62140
    assert austin.asking_price == 28900
    assert austin.region == "TX" and austin.zip == "78701"
    assert austin.lat == pytest.approx(30.2672)
    assert austin.lng == pytest.approx(-97.7431)
    assert austin.sold_price is None

    denver = by_id["ebay:222"]
    assert denver.lat == 39.0 and denver.lng == -104.9
    assert denver.sold_price == 41000
    assert denver.sold_at is not None
    assert denver.zip == "80202"

    japan = by_id["ebay:333"]
    assert japan.lat is None and japan.lng is None
    assert japan.region is None


def test_robots_disallow_skips_the_api():
    web = Web(DISALLOW)
    adapter, _ticker = _adapter(web)
    with pytest.raises(RobotsDisallowed):
        adapter.fetch("BMW M3")
    assert len(web.calls) == 1
    assert web.calls[0][0].endswith("/robots.txt")


def test_missing_app_id_does_not_fetch(monkeypatch):
    monkeypatch.delenv("EBAY_APP_ID", raising=False)

    def boom(url, headers):
        raise AssertionError(url)

    adapter = EbayFindingAdapter(app_id="", transport=boom, min_interval_s=0)
    with pytest.raises(MissingAppId):
        adapter.fetch("BMW M3")


def test_bad_ack_raises():
    web = Web(ALLOW, api_body=json.dumps({"findItemsAdvancedResponse": [{"ack": ["Failure"]}]}))
    adapter, _ticker = _adapter(web)
    with pytest.raises(EbayFindingError):
        adapter.fetch("BMW M3")
