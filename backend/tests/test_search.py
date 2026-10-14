"""Radius search and the listing fields the search page filters on."""

from __future__ import annotations

from shared.schemas.deal import DealPayload, DealSource, ListingData


def test_radius_search_uses_fixture_cities(client):
    near = client.get("/search/listings", params={"location": "Austin, TX", "radius_miles": 50})
    assert near.status_code == 200
    body = near.json()
    assert body["center"]["resolved_by"] == "fixture_gazetteer"
    assert {item["location"] for item in body["listings"]} == {"Austin, TX"}
    assert body["listings"][0]["make"] == "BMW"
    assert body["listings"][0]["geo_source"] == "fixture_gazetteer"
    assert "fixture city gazetteer" in body["note"]

    regional = client.get(
        "/search/listings",
        params={"location": "Austin, TX", "radius_miles": 900},
    )
    places = {item["location"] for item in regional.json()["listings"]}
    assert places == {"Austin, TX", "Denver, CO", "Atlanta, GA"}

    wide = client.get("/search/listings", params={"location": "austin", "radius_miles": 2000})
    places = {item["location"] for item in wide.json()["listings"]}
    assert "Portland, OR" in places
    assert "Japan" not in places


def test_coordinates_and_unknown_location(client):
    coords = client.get(
        "/search/listings",
        params={"lat": 30.2672, "lng": -97.7431, "radius_miles": 50},
    )
    assert coords.status_code == 200
    assert coords.json()["center"]["resolved_by"] == "coordinates"
    assert coords.json()["listings"][0]["make"] == "BMW"

    pair = client.get(
        "/search/listings",
        params={"location": "30.2672, -97.7431", "radius_miles": 50},
    )
    assert pair.status_code == 200
    assert pair.json()["listings"][0]["location"] == "Austin, TX"

    missing = client.get("/search/listings", params={"location": "Nowhereville"})
    assert missing.status_code == 400
    assert "fixture" in missing.json()["detail"]

    assert client.get("/search/listings", params={"lat": 30.2}).status_code == 400


def test_basic_filters(client):
    bmw = client.get(
        "/search/listings",
        params={
            "location": "Austin, TX",
            "radius_miles": 2500,
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


def test_places_are_labeled_fixture(client):
    response = client.get("/search/places")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fixture_gazetteer"
    labels = {place["label"] for place in body["places"]}
    assert {"Austin, TX", "Denver, CO", "Atlanta, GA", "Japan"} <= labels


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
    fixture = to_hit(payload)
    assert fixture.geo_source == "fixture_gazetteer"
    assert fixture.lat == 30.2672

    # Stand-in for a listing that already carries coordinates. ListingData on
    # main does not declare them; Builder's ingestion branch will.
    class Located:
        title = "2001 Example"
        price = 12000
        year = 2001
        make = "BMW"
        model = "M3"
        mileage = 50000
        location = "Austin, TX"
        latitude = 39.0
        longitude = -104.0

    class Deal:
        deal_id = "located"
        listing = Located()
        deal_score = None
        deal_tier = None

    listed = to_hit(Deal(), center=(39.0, -104.0))
    assert listed.geo_source == "listing"
    assert listed.lat == 39.0
    assert listed.lng == -104.0
    assert listed.distance_miles == 0.0


def test_deals_feed_is_unchanged(client):
    deals = client.get("/deals").json()
    assert len(deals) == 5
    assert "lat" not in deals[0]
