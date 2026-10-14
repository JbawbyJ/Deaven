"""Radius search and the listing fields the search page filters on."""

from __future__ import annotations

from shared.schemas.deal import DealPayload, DealSource, ListingData


def test_seeded_listings_are_not_pinned_without_coordinates(client):
    listed = client.get("/search/listings")
    assert listed.status_code == 200
    body = listed.json()
    assert body["center"] is None
    assert body["total"] == 5
    assert body["without_coordinates"] == 5
    assert all(item["lat"] is None and item["lng"] is None for item in body["listings"])
    assert "not on the map" in body["note"]

    radius = client.get(
        "/search/listings",
        params={"lat": 30.2672, "lng": -97.7431, "radius_miles": 500},
    )
    assert radius.status_code == 200
    body = radius.json()
    assert body["total"] == 0
    assert body["listings"] == []
    assert body["without_coordinates"] == 5
    assert "left out of this radius" in body["note"]

    city = client.get("/search/listings", params={"location": "Austin, TX"})
    assert city.status_code == 400
    assert "not geocoded" in city.json()["detail"]


def test_coordinates_and_unknown_location(client):
    pair = client.get(
        "/search/listings",
        params={"location": "30.2672, -97.7431", "radius_miles": 50},
    )
    assert pair.status_code == 200
    assert pair.json()["center"]["label"] == "30.2672, -97.7431"
    assert pair.json()["total"] == 0
    assert pair.json()["without_coordinates"] == 5

    missing = client.get("/search/listings", params={"location": "Nowhereville"})
    assert missing.status_code == 400
    assert "lat" in missing.json()["detail"]

    assert client.get("/search/listings", params={"lat": 30.2}).status_code == 400


def test_basic_filters(client):
    bmw = client.get(
        "/search/listings",
        params={
            "make": "BMW",
            "model": "M3",
            "year_min": 2000,
            "year_max": 2006,
            "price_max": 30000,
            "mileage_max": 80000,
        },
    )
    assert bmw.status_code == 200
    listings = bmw.json()["listings"]
    assert len(listings) == 1
    assert listings[0]["model"] == "M3"

    none = client.get("/search/listings", params={"make": "BMW", "price_min": 100000})
    assert none.status_code == 200
    assert none.json()["total"] == 0
    assert none.json()["center"] is None


def test_zip_and_region_do_not_need_a_city(client):
    by_zip = client.get("/search/listings", params={"location": "78701"})
    assert by_zip.status_code == 200
    assert by_zip.json()["center"] is None
    assert by_zip.json()["total"] == 0

    by_region = client.get("/search/listings", params={"region": "tx"})
    assert by_region.status_code == 200
    assert by_region.json()["total"] == 0

    unknown = client.get("/search/listings", params={"location": "Nowhereville"})
    assert unknown.status_code == 400


def test_adapter_uses_listing_id_region_zip_and_coordinates(monkeypatch):
    from backend.search.service import search_deals

    class Listing:
        title = "1998 Example"
        price = 10000
        year = 1998
        make = "Honda"
        model = "Civic"
        mileage = 1000
        location = "Austin, TX"
        region = "tx"
        zip = "78701"
        listing_id = "manual:civic-1"
        lat = 30.27
        lng = -97.74

    class Unmapped:
        title = "No pin"
        price = 8000
        location = "Austin, TX"
        listing_id = "manual:none"

    class Far:
        title = "Seattle"
        price = 11000
        listing_id = "manual:far"
        lat = 47.6062
        lng = -122.3321

    class Deal:
        def __init__(self, listing, deal_id):
            self.deal_id = deal_id
            self.listing = listing
            self.deal_score = 10
            self.deal_tier = "pass"

    monkeypatch.setattr(
        "backend.search.service.list_deals",
        lambda limit=1000: [
            Deal(Listing(), "pipeline-id"),
            Deal(Unmapped(), "no-pin"),
            Deal(Far(), "far-id"),
        ],
    )

    hit = search_deals(region="TX", zip_code="78701").listings[0]
    assert hit.listing_id == "manual:civic-1"
    assert hit.deal_id == "pipeline-id"
    assert hit.region == "TX"
    assert hit.zip == "78701"
    assert hit.lat == 30.27
    assert hit.lng == -97.74

    by_location_zip = search_deals(location="78701")
    assert by_location_zip.center is None
    assert [item.listing_id for item in by_location_zip.listings] == ["manual:civic-1"]

    by_region = search_deals(location="tx")
    assert [item.listing_id for item in by_region.listings] == ["manual:civic-1"]

    missed = search_deals(region="OR")
    assert missed.total == 0

    near = search_deals(lat=30.2672, lng=-97.7431, radius_miles=50)
    assert [item.listing_id for item in near.listings] == ["manual:civic-1"]
    assert near.without_coordinates == 1
    assert "left out of this radius" in near.note
    assert near.listings[0].distance_miles < 1


def test_adapter_prefers_coordinates_when_the_listing_has_them():
    from backend.search.adapter import to_hit

    payload = DealPayload(
        source=DealSource.MANUAL,
        url="https://example.com/car",
        listing=ListingData(
            title="2001 Example",
            price=12000,
            year=2001,
            make="BMW",
            model="M3",
            mileage=50000,
            location="Austin, TX",
        ),
    )
    plain = to_hit(payload)
    assert plain.lat is None
    assert plain.lng is None

    class Located:
        title = "2001 Example"
        price = 12000
        year = 2001
        make = "BMW"
        model = "M3"
        mileage = 50000
        location = "Denver, CO"
        lat = 39.0
        lng = -104.0

    class CityOnly:
        title = "City name only"
        price = 9000
        location = "Austin, TX"
        latitude = 30.27
        longitude = -97.74

    class Deal:
        def __init__(self, listing, deal_id):
            self.deal_id = deal_id
            self.listing = listing
            self.deal_score = None
            self.deal_tier = None

    listed = to_hit(Deal(Located(), "located"), center=(39.0, -104.0))
    assert listed.lat == 39.0
    assert listed.lng == -104.0
    assert listed.distance_miles == 0.0

    unnamed = to_hit(Deal(CityOnly(), "city"))
    assert unnamed.lat is None
    assert unnamed.lng is None


def test_deals_feed_is_unchanged(client):
    deals = client.get("/deals").json()
    assert len(deals) == 5
    assert "lat" not in deals[0]
