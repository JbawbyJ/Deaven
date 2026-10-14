"""eBay Browse adapter. Fixture responses only — no live network."""

from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path

import pytest

from backend.ingestion.ebay_browse import (
    TOKEN_URL,
    EbayBrowseAdapter,
    EbayBrowseError,
    MissingCredentials,
)
from backend.ingestion.http import USER_AGENT, RobotsDisallowed

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingestion"
SEARCH = (FIXTURES / "browse_search.json").read_text()
TOKEN = (FIXTURES / "oauth_token.json").read_text()
ALLOW = (FIXTURES / "robots_allow.txt").read_text()
DISALLOW = (FIXTURES / "robots_disallow.txt").read_text()
CLIENT_ID = "test-client"
CLIENT_SECRET = "test-secret"


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
    def __init__(
        self,
        robots: str,
        search_status: int = 200,
        search_body: str | None = None,
        token_status: int = 200,
        token_body: str | None = None,
    ) -> None:
        self.robots = robots
        self.search_status = search_status
        self.search_body = SEARCH if search_body is None else search_body
        self.token_status = token_status
        self.token_body = TOKEN if token_body is None else token_body
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(
        self,
        url: str,
        headers: dict[str, str],
        method: str = "GET",
        body: bytes | None = None,
    ) -> tuple[int, str]:
        self.calls.append((method, url, headers, body))
        if url.endswith("/robots.txt"):
            return 200, self.robots
        if url == TOKEN_URL or url.startswith(TOKEN_URL + "?"):
            return self.token_status, self.token_body
        return self.search_status, self.search_body


def _adapter(web: Web, **kwargs) -> tuple[EbayBrowseAdapter, Ticker]:
    ticker = Ticker()
    adapter = EbayBrowseAdapter(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        transport=web,
        min_interval_s=0,
        clock=ticker.clock,
        sleep=ticker.sleep,
        **kwargs,
    )
    return adapter, ticker


def _posts(web: Web) -> list[tuple[str, dict[str, str], bytes | None]]:
    return [(url, headers, body) for method, url, headers, body in web.calls if method == "POST"]


def test_fetch_maps_browse_items_and_caches_nothing_sensitive(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("live network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    web = Web(ALLOW)
    adapter, ticker = _adapter(web)
    listings = adapter.fetch("BMW M3", price_min=1000)

    assert ticker.sleeps == [5.0, 5.0]
    methods = [method for method, _url, _headers, _body in web.calls]
    assert methods == ["GET", "POST", "GET"]
    assert web.calls[0][1].endswith("/robots.txt")
    assert web.calls[0][2]["User-Agent"] == USER_AGENT

    token_url, token_headers, token_body = _posts(web)[0]
    assert token_url == TOKEN_URL
    decoded = base64.b64decode(token_headers["Authorization"].removeprefix("Basic ")).decode()
    assert decoded == f"{CLIENT_ID}:{CLIENT_SECRET}"
    assert token_body is not None
    assert b"grant_type=client_credentials" in token_body

    search_url, search_headers = web.calls[2][1], web.calls[2][2]
    assert "/buy/browse/v1/item_summary/search" in search_url
    assert "category_ids=6001" in search_url
    assert "1000" in search_url
    assert search_headers["Authorization"] == "Bearer fixture-token"
    assert search_headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_MOTORS"
    assert search_headers["User-Agent"] == USER_AGENT
    assert CLIENT_SECRET not in search_url

    by_id = {item.listing_id: item for item in listings}
    assert set(by_id) == {"ebay:v1|111|0", "ebay:v1|222|0", "ebay:v1|333|0"}

    austin = by_id["ebay:v1|111|0"]
    assert austin.source_id == "v1|111|0"
    assert austin.vin == "1HGCM82633A004352"
    assert austin.year == 2003 and austin.make == "BMW" and austin.model == "M3"
    assert austin.trim == "Coupe"
    assert austin.trim_normalized == "coupe"
    assert austin.mileage == 62140
    assert austin.asking_price == 28900
    assert austin.region == "TX" and austin.zip == "78701"
    assert austin.location == "Austin, TX"
    assert austin.lat == pytest.approx(30.2672)
    assert austin.lng == pytest.approx(-97.7431)

    denver = by_id["ebay:v1|222|0"]
    assert denver.vin is None
    assert denver.region == "CO" and denver.zip == "80202"
    assert denver.lat == pytest.approx(39.7392)
    assert denver.lng == pytest.approx(-104.9903)

    japan = by_id["ebay:v1|333|0"]
    assert japan.asking_price == 62000
    assert japan.lat is None and japan.lng is None
    assert japan.region is None

    dumped = json.dumps([item.model_dump(mode="json") for item in listings])
    assert CLIENT_SECRET not in dumped
    assert CLIENT_ID not in dumped


def test_token_is_reused_until_it_expires():
    web = Web(ALLOW)
    adapter, ticker = _adapter(web)
    adapter.fetch("BMW M3")
    adapter.fetch("BMW M3")
    assert len(_posts(web)) == 1

    ticker.now = 8000
    adapter.fetch("BMW M3")
    assert len(_posts(web)) == 2


def test_robots_disallow_skips_token_and_search():
    web = Web(DISALLOW)
    adapter, _ticker = _adapter(web)
    with pytest.raises(RobotsDisallowed):
        adapter.fetch("BMW M3")
    assert len(web.calls) == 1
    assert web.calls[0][1].endswith("/robots.txt")


def test_missing_credentials_do_not_fetch(monkeypatch):
    monkeypatch.setenv("EBAY_APP_ID", "retired-finding-key")
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)

    def boom(url, headers, method="GET", body=None):
        raise AssertionError(url)

    adapter = EbayBrowseAdapter(client_id="", client_secret="", transport=boom, min_interval_s=0)
    with pytest.raises(MissingCredentials):
        adapter.fetch("BMW M3")


def test_token_http_error_skips_search():
    web = Web(ALLOW, token_status=401, token_body='{"error":"invalid_client"}')
    adapter, _ticker = _adapter(web)
    with pytest.raises(EbayBrowseError, match="OAuth"):
        adapter.fetch("BMW M3")
    assert not any("/item_summary/search" in url for _method, url, _headers, _body in web.calls)


def test_browse_errors_raise():
    web = Web(ALLOW, search_body=json.dumps({"errors": [{"errorId": 12001}]}))
    adapter, _ticker = _adapter(web)
    with pytest.raises(EbayBrowseError, match="errors"):
        adapter.fetch("BMW M3")
