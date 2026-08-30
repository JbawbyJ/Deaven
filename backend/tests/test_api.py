from __future__ import annotations

SWAGGER_PATHS = {
    "/health",
    "/deals/ingest",
    "/deals",
    "/deals/{deal_id}",
    "/deals/{deal_id}/outcome",
    "/deals/{deal_id}/decision",
    "/watchlists",
    "/watchlists/{filter_id}",
    "/stats/pipeline",
    "/scout/run",
}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["pipeline_mode"] == "local"
    assert body["scout_backend"] == "local"
    assert body["scheduler_enabled"] is False
    assert "last_scout" in body
    assert body["last_scout"]["filters"] == 0
    assert body["last_scout"]["new_listings"] == 0


def test_openapi_matches_swagger_contract(client):
    spec = client.get("/openapi.json").json()
    assert SWAGGER_PATHS.issubset(spec["paths"].keys())


def test_list_deals_returns_seeded_catalog(client):
    response = client.get("/deals")
    assert response.status_code == 200
    deals = response.json()
    assert len(deals) == 5
    assert all(deal["deal_score"] is not None for deal in deals)
    assert {deal["deal_tier"] for deal in deals} >= {"fire", "strong", "watchlist", "pass"}


def test_deal_detail_and_decision(client):
    deals = client.get("/deals").json()
    deal_id = deals[0]["deal_id"]

    detail = client.get(f"/deals/{deal_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["listing"]["title"]
    assert body["score_components"]["price_score"] is not None
    assert body["narrative"]
    assert not body["narrative"].startswith("DEALTIER")
    assert body["narrative"].split("—")[0].strip() in {
        "FIRE",
        "STRONG",
        "WATCHLIST",
        "PASS",
        "DISCARD",
    }

    decision = client.post(f"/deals/{deal_id}/decision", params={"decision": "acquire"})
    assert decision.status_code == 200
    updated = client.get(f"/deals/{deal_id}").json()
    assert updated["human_decision"] == "acquire"
    assert updated["status"] == "actioned"


def test_ingest_catalog_slug_is_idempotent(client):
    first = client.post("/deals/ingest", json={"url": "local://bmw-m3-2003"})
    assert first.status_code == 200
    body = first.json()
    assert body["make"] == "BMW"
    assert body["model"] == "M3"
    assert body["deal_score"] > 0

    second = client.post("/deals/ingest", json={"url": "local://bmw-m3-2003"})
    assert second.status_code == 200
    assert second.json()["deal_id"] == body["deal_id"]
    assert len(client.get("/deals").json()) == 5


def test_ingest_unknown_url_creates_heuristic_deal(client):
    response = client.post(
        "/deals/ingest",
        json={"url": "https://bringatrailer.com/listing/2001-bmw-m3-manual"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "bat"
    assert body["year"] == 2001
    assert len(client.get("/deals").json()) == 6


def test_tier_filter_and_stats(client):
    fire = client.get("/deals", params={"tier": "fire"}).json()
    assert fire
    assert all(deal["deal_tier"] == "fire" for deal in fire)

    stats = client.get("/stats/pipeline").json()
    assert stats["total_ingested"] == 5
    assert stats["fire_deals"] >= 1
    assert stats["avg_score"] > 0


def test_watchlists_round_trip(client):
    seeded = client.get("/watchlists").json()
    assert any(item["name"] == "E46 M3 Hunt" for item in seeded)

    created = client.post(
        "/watchlists",
        json={
            "name": "FD RX-7",
            "makes": ["Mazda"],
            "models": ["RX-7"],
            "year_min": 1992,
            "year_max": 1995,
        },
    )
    assert created.status_code == 200
    filter_id = created.json()["filter_id"]
    names = {item["name"] for item in client.get("/watchlists").json()}
    assert "FD RX-7" in names

    deleted = client.delete(f"/watchlists/{filter_id}")
    assert deleted.status_code == 200
    names = {item["name"] for item in client.get("/watchlists").json()}
    assert "FD RX-7" not in names


def test_scout_run_local_produces_deals(client):
    watchlists = client.get("/watchlists").json()
    hunt = next(item for item in watchlists if item["name"] == "E46 M3 Hunt")

    response = client.post("/scout/run", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["ran"] >= 1
    assert body["new_listings"] >= 1
    assert hunt["filter_id"] in body["filter_ids"]
    assert isinstance(body["tiers"], dict)
    assert body["tiers"]

    deals = client.get("/deals").json()
    assert deals
    assert any(deal["make"] == "BMW" and deal["model"] == "M3" for deal in deals)

    targeted = client.post("/scout/run", json={"filter_id": hunt["filter_id"]})
    assert targeted.status_code == 200
    targeted_body = targeted.json()
    assert targeted_body["ran"] == 1
    assert targeted_body["filter_ids"] == [hunt["filter_id"]]
    assert targeted_body["new_listings"] >= 1

    health = client.get("/health").json()
    assert health["scout_backend"] == "local"
    assert health["scheduler_enabled"] is False
    assert health["last_scout"]["filters"] == 1
    assert health["last_scout"]["new_listings"] == targeted_body["new_listings"]
    assert health["last_scout"]["at"]


def test_odometer_rollback_hard_zero(client):
    response = client.post(
        "/deals/ingest",
        json={"url": "https://bringatrailer.com/listing/2002-bmw-m3-odometer-rollback"},
    )
    assert response.status_code == 200
    deal_id = response.json()["deal_id"]
    detail = client.get(f"/deals/{deal_id}").json()
    assert detail["deal_score"] == 0
    assert detail["risk_report"]["auto_disqualify"] is True
    assert "odometer_rollback" in detail["risk_report"]["title_flags"]


def test_outcome_patch_records_sale(client):
    deals = client.get("/deals").json()
    deal_id = deals[0]["deal_id"]
    response = client.patch(
        f"/deals/{deal_id}/outcome",
        json={
            "purchase_price": 20000,
            "sale_price": 28000,
            "days_to_sell": 12,
            "recon_actual": 1500,
            "lemon": False,
        },
    )
    assert response.status_code == 200
    detail = client.get(f"/deals/{deal_id}").json()
    assert detail["outcome_purchase_price"] == 20000
    assert detail["outcome_sale_price"] == 28000
    assert detail["status"] == "sold"
    assert detail["outcome_margin_actual"] is not None
