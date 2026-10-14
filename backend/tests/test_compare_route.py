"""HTTP compare route. Synthetic deals only."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.db.client import save_deal
from backend.pricing.history import PriceHistoryStore
from shared.schemas.deal import DealPayload, DealSource, ListingData

ROW_FIELDS = {
    "listing_id",
    "year",
    "make",
    "model",
    "trim",
    "mileage",
    "region",
    "asking_price",
    "estimate",
    "confidence",
    "deal_rating",
    "price_history",
    "delta_vs_cheapest",
    "delta_vs_estimate",
    "delta_vs_estimate_pct",
    "best_value",
}


def _seed_ids(client, count=2) -> list[str]:
    deals = client.get("/deals").json()
    return [deal["deal_id"] for deal in deals[:count]]


def _save_m3(deal_id: str, price: float) -> None:
    save_deal(
        DealPayload(
            deal_id=deal_id,
            source=DealSource.MANUAL,
            url=f"https://example.com/{deal_id}",
            listing=ListingData(
                title=f"2003 BMW M3 {deal_id}",
                price=price,
                year=2003,
                make="BMW",
                model="M3",
                trim="Coupe",
                mileage=60_000,
            ),
        )
    )


def test_compare_route_keeps_order_and_reports_insufficient(client):
    ids = _seed_ids(client, 2)
    response = client.post("/compare", json={"ids": list(reversed(ids))})
    assert response.status_code == 200
    rows = response.json()
    assert [row["listing_id"] for row in rows] == list(reversed(ids))
    assert sum(row["best_value"] for row in rows) == 1
    for row in rows:
        assert set(row) == ROW_FIELDS
        assert row["confidence"] == "insufficient"
        assert row["deal_rating"] == "unknown"
        assert row["estimate"] is None
        assert row["delta_vs_estimate"] is None
        assert row["delta_vs_estimate_pct"] is None
        assert row["price_history"] is None
        assert row["asking_price"] > 0


def test_compare_route_rates_one_best_value_and_a_down_trend(client):
    _save_m3("m3-high", 42_000)
    _save_m3("m3-mid", 41_000)
    _save_m3("m3-ask", 40_000)
    _save_m3("m3-deal", 32_000)
    observed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    later = datetime(2026, 1, 11, tzinfo=timezone.utc)
    PriceHistoryStore().record("m3-deal", 45_000, observed)
    PriceHistoryStore().record("m3-deal", 32_000, later)

    ids = ["m3-high", "m3-mid", "m3-ask", "m3-deal"]
    response = client.post("/compare", json={"ids": ids})
    assert response.status_code == 200
    body = response.json()
    assert [row["listing_id"] for row in body] == ids
    rows = {row["listing_id"]: row for row in body}

    deal = rows["m3-deal"]
    assert deal["asking_price"] == 32_000
    assert deal["estimate"] == 41_000
    assert deal["confidence"] == "low"
    assert deal["deal_rating"] == "great"
    assert deal["delta_vs_cheapest"] == 0
    assert deal["delta_vs_estimate"] == -9_000
    assert deal["delta_vs_estimate_pct"] == round(-9_000 / 41_000, 4)
    assert deal["best_value"] is True
    assert deal["price_history"]["trend"] == "down"
    assert deal["price_history"]["current_price"] == 32_000
    assert deal["price_history"]["first_price"] == 45_000
    assert deal["year"] == 2003
    assert deal["make"] == "BMW"
    assert deal["trim"] == "Coupe"
    assert deal["mileage"] == 60_000

    assert rows["m3-ask"]["deal_rating"] == "fair"
    assert rows["m3-ask"]["best_value"] is False
    assert rows["m3-ask"]["price_history"] is None
    assert rows["m3-high"]["delta_vs_cheapest"] == 10_000
    assert sum(row["best_value"] for row in body) == 1


def test_compare_get_matches_post(client):
    ids = _seed_ids(client, 3)
    posted = client.post("/compare", json={"ids": ids}).json()
    queried = client.get("/compare", params={"ids": f" {ids[0]} , {ids[1]} , {ids[2]} "})
    assert queried.status_code == 200
    assert queried.json() == posted


def test_compare_route_rejects_bad_selections(client):
    ids = _seed_ids(client, 5)
    assert client.post("/compare", json={"ids": ids[:1]}).status_code == 400
    assert client.post("/compare", json={"ids": ids}).status_code == 400
    assert client.post("/compare", json={"ids": [ids[0], ids[0]]}).status_code == 400
    assert client.post("/compare", json={"ids": ["  ", ids[0]]}).status_code == 400
    missing = client.post("/compare", json={"ids": [ids[0], "missing-listing"]})
    assert missing.status_code == 404
    assert "missing-listing" in missing.json()["detail"]
    assert client.get("/compare", params={"ids": ids[0]}).status_code == 400
