"""Synthetic price observations. No scraped listings."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.pricing.history import PriceHistoryStore, PriceObservation, summarize_history


def _at(day: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)


def test_summary_reports_drops_changes_and_trend():
    listing_id = "bat:1"
    rows = [
        PriceObservation(listing_id, 45_000, _at(0)),
        PriceObservation(listing_id, 42_000, _at(10)),
        PriceObservation(listing_id, 43_000, _at(12)),
        PriceObservation(listing_id, 40_000, _at(20)),
    ]
    summary = summarize_history(listing_id, rows, as_of=_at(25))
    assert summary.first_price == 45_000
    assert summary.current_price == 40_000
    assert summary.total_drop_amount == 5_000
    assert summary.total_drop_pct == round(5_000 / 45_000, 4)
    assert summary.last_drop_amount == 3_000
    assert summary.last_drop_pct == round(3_000 / 43_000, 4)
    assert summary.change_count == 3
    assert summary.days_on_market == 25
    assert summary.trend == "down"


def test_rise_has_no_drop_and_trends_up():
    rows = [
        PriceObservation("ebay:2", 20_000, _at(0)),
        PriceObservation("ebay:2", 22_000, _at(3)),
    ]
    summary = summarize_history("ebay:2", rows)
    assert summary.total_drop_amount == 0
    assert summary.total_drop_pct == 0
    assert summary.last_drop_amount is None
    assert summary.last_drop_pct is None
    assert summary.change_count == 1
    assert summary.days_on_market == 3
    assert summary.trend == "up"


def test_unchanged_price_is_flat():
    rows = [PriceObservation("manual:3", 10_000, _at(0))]
    summary = summarize_history("manual:3", rows)
    assert summary.change_count == 0
    assert summary.days_on_market == 0
    assert summary.trend == "flat"
    assert summary.last_drop_amount is None


def test_empty_history():
    summary = summarize_history("missing", [])
    assert summary.current_price is None
    assert summary.first_price is None
    assert summary.trend == "unknown"
    assert summary.days_on_market is None


def test_store_reloads_and_replaces_same_timestamp(tmp_path):
    path = tmp_path / "price_history.json"
    store = PriceHistoryStore(path)
    store.record("bat:1", 45_000, _at(10))
    store.record("bat:1", 44_000, _at(0))
    store.record("bat:1", 43_500, _at(0))
    store.record("cab:9", 12_000, _at(1))

    reloaded = PriceHistoryStore(path)
    summary = reloaded.summary("bat:1")
    assert [row.price for row in reloaded.observations("bat:1")] == [43_500, 45_000]
    assert summary.first_price == 43_500
    assert summary.current_price == 45_000
    assert summary.trend == "up"
    assert summary.total_drop_amount == 0
    assert reloaded.summary("cab:9").current_price == 12_000
    assert reloaded.summary("other").trend == "unknown"


def test_record_rejects_bad_input(tmp_path):
    store = PriceHistoryStore(tmp_path / "price_history.json")
    with pytest.raises(ValueError):
        store.record("  ", 1, _at(0))
    with pytest.raises(ValueError):
        store.record("bat:1", -1, _at(0))
