"""Search fixture endpoint. Does not import the unmerged listing schema."""

from __future__ import annotations

import hashlib


def test_search_fixtures_follow_pr8_vehicle_key(client):
    response = client.get("/api/listings/search")
    assert response.status_code == 200
    body = response.json()
    assert "5bc43fe" in body["note"]
    assert "9cff34b" in body["note"]
    assert "no zip field" in body["note"]
    assert body["total"] == 5

    by_source = {item["source"]: item for item in body["listings"]}
    bat = by_source["bat"]
    ebay = by_source["ebay"]
    assert bat["vehicle_key"] == ebay["vehicle_key"] == "1HGCM82633A004352"
    assert bat["vin"] == ebay["vin"] == "1HGCM82633A004352"
    assert bat["observation_id"] == "bd8f0e137da82645"
    assert ebay["observation_id"] == "873b796649b684da"
    assert bat["location"]["latitude"] == 30.2672
    assert bat["location"]["longitude"] == -97.7431
    assert "zip" not in bat["location"]
    asking = [row["amount"] for row in bat["prices"] if row["kind"] == "asking"]
    assert asking[-1] < asking[0]
    assert asking[-1] == bat["price"]
    assert bat["source_detail"]["name"] == "Bring a Trailer"
    assert bat["source_detail"]["robots_ok"] is False
    assert bat["seller"]["seller_type"] == "auction"

    m3_cluster = next(cluster for cluster in body["clusters"] if cluster["match_method"] == "vin")
    assert m3_cluster["vehicle_key"] == "1HGCM82633A004352"
    assert m3_cluster["listing_ids"] == ["bd8f0e137da82645", "873b796649b684da"]

    rx7 = by_source["hemmings"]
    expected_rx7 = hashlib.sha256(b"1993|mazda|rx-7|touring|70000-79999|97202").hexdigest()
    assert rx7["vin"] is None
    assert rx7["vin_note"] == "missing"
    assert rx7["vehicle_key"] == expected_rx7
    assert rx7["match_method"] == "fuzzy"
    assert rx7["location"]["latitude"] is None

    legend = by_source["craigslist"]
    expected_legend = hashlib.sha256(b"1991|acura|legend|l|140000-149999|80202").hexdigest()
    assert legend["vin"] is None
    assert legend["vin_note"] == "invalid"
    assert legend["vehicle_key"] == expected_legend
    assert legend["price"] == 18000

    m3_priced = next(cluster for cluster in body["clusters"] if cluster["vehicle_key"] == "1HGCM82633A004352")
    assert m3_priced["result"]["deal_score"] == round((40000 - 31200) / 40000, 4)
    assert m3_priced["result"]["deal_score"] > 0
    assert m3_priced["result"]["deal_rating"] == "great"
    assert m3_priced["result"]["estimate"] == {"low": 36000, "mid": 40000, "high": 46000}
    assert 0 <= m3_priced["result"]["confidence"] <= 1
    assert m3_priced["result"]["comp_count"] == 4

    legend_cluster = next(cluster for cluster in body["clusters"] if cluster["match_method"] == "fuzzy" and cluster["listing_ids"] == [legend["observation_id"]])
    assert legend_cluster["result"]["deal_score"] is None
    assert legend_cluster["result"]["deal_rating"] is None
    assert legend_cluster["result"]["estimate"] == {"low": None, "mid": None, "high": None}
    assert legend_cluster["result"]["confidence"] == 0
    assert legend_cluster["result"]["comp_count"] == 0

    s2000 = by_source["autotrader"]
    assert s2000["model"] == "S2000"
    assert s2000["price"] == 27500
    s2000_cluster = next(cluster for cluster in body["clusters"] if cluster["listing_ids"] == [s2000["observation_id"]])
    assert s2000_cluster["result"]["deal_rating"] == "high"
    assert s2000_cluster["result"]["deal_score"] == round((24000 - 27500) / 24000, 4)
    assert s2000_cluster["result"]["deal_score"] < -0.05
    assert s2000_cluster["result"]["estimate"] == {"low": 22000, "mid": 24000, "high": 25500}


def test_search_filters_make_mileage_and_radius(client):
    bmw = client.get("/api/listings/search", params={"make": "bmw", "mileage_max": 70000})
    assert {item["source"] for item in bmw.json()["listings"]} == {"bat", "ebay"}

    austin = client.get(
        "/api/listings/search",
        params={"location": "Austin, TX", "radius": 50},
    )
    assert {item["model"] for item in austin.json()["listings"]} == {"M3"}
    assert all(item["distance_miles"] < 1 for item in austin.json()["listings"])

    denver = client.get(
        "/api/listings/search",
        params={"location": "Denver", "radius": 30},
    )
    assert denver.json()["listings"] == []


def test_unknown_location_is_empty(client):
    response = client.get("/api/listings/search", params={"location": "Nowhereville"})
    assert response.status_code == 200
    assert response.json()["listings"] == []
