"""VIN and fuzzy dedupe on ListingData. No network."""

from __future__ import annotations

from backend.ingestion.dedupe import dedupe
from shared.schemas.deal import ListingData

VIN_A = "1HGCM82633A004352"
VIN_B = "1M8GDM9AXKP042788"


def _row(**overrides) -> ListingData:
    data = {
        "title": "2003 BMW M3 Coupe",
        "price": 28000,
        "year": 2003,
        "make": "BMW",
        "model": "M3",
        "trim": "Coupe",
        "mileage": 60000,
        "region": "TX",
        "zip": "78701",
        "source": "ebay",
        "source_id": "1",
    }
    data.update(overrides)
    return ListingData(**data)


def test_same_vin_merges_and_keeps_both_source_rows():
    ebay = _row(source_id="1", vin=VIN_A, price=28000, region="TX", zip="78701")
    bat = _row(source="bat", source_id="9", vin=VIN_A, price=31000, region="CO", zip="80202")
    clusters = dedupe([ebay, bat])
    assert len(clusters) == 1
    assert clusters[0].canonical_id == f"vin:{VIN_A}"
    assert {row.listing_id for row in clusters[0].records} == {"ebay:1", "bat:9"}
    assert ebay.canonical_id == bat.canonical_id == f"vin:{VIN_A}"


def test_different_vins_do_not_fuzzy_merge():
    left = _row(source_id="1", vin=VIN_A)
    right = _row(source="bat", source_id="2", vin=VIN_B)
    clusters = dedupe([left, right])
    assert {cluster.canonical_id for cluster in clusters} == {f"vin:{VIN_A}", f"vin:{VIN_B}"}
    assert all(len(cluster.records) == 1 for cluster in clusters)


def test_fuzzy_match_on_year_make_model_trim_mileage_place_and_price():
    left = _row(source_id="4", mileage=60200, price=28200)
    right = _row(source="bat", source_id="5", make="bmw", model="m3", mileage=60400, price=28300)
    clusters = dedupe([left, right])
    assert len(clusters) == 1
    assert clusters[0].canonical_id.startswith("fuzzy:")
    assert len(clusters[0].records) == 2
    assert left.canonical_id == right.canonical_id


def test_fuzzy_rejects_mileage_trim_place_and_price_gaps():
    base = _row(source_id="4")
    far_miles = _row(source="bat", source_id="6", mileage=90000)
    other_trim = _row(source="classic_com", source_id="7", trim="Sedan")
    other_region = _row(source="hemmings", source_id="8", zip=None, region="CO")
    base_region = _row(source="tcv", source_id="18", zip=None, region="TX")
    expensive = _row(source="cab", source_id="14", price=45000)
    assert len(dedupe([base, far_miles])) == 2
    assert len(dedupe([base, other_trim])) == 2
    assert len(dedupe([base_region, other_region])) == 2
    assert len(dedupe([base, expensive])) == 2


def test_same_zip_matches_and_vin_anchors_a_row_without_one():
    labeled = _row(source_id="10", region="TX", zip="78701")
    plus4 = _row(source="bat", source_id="11", region="Texas", zip="78701-9999")
    zipped = dedupe([labeled, plus4])
    assert len(zipped) == 1

    with_vin = _row(source_id="12", vin=VIN_A)
    without = _row(source="bat", source_id="13")
    anchored = dedupe([with_vin, without])
    assert len(anchored) == 1
    assert anchored[0].canonical_id == f"vin:{VIN_A}"
    assert {row.source for row in anchored[0].records} == {"ebay", "bat"}


def test_empty_input():
    assert dedupe([]) == []
