"""
In-process JSON store for local development.

Persists deals and watchlists to DEAVEN_DATA_DIR/local_store.json so a
reviewer can restart the API without losing the demo feed.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

from backend.core.settings import seed_demo_deals, store_path
from shared.schemas.deal import DealPayload, DealStatus, DealTier, WatchlistFilter

logger = logging.getLogger(__name__)


def _tier_value(value) -> Optional[str]:
    if value is None:
        return None
    return value.value if isinstance(value, DealTier) else str(value)


def _status_value(value) -> Optional[str]:
    if value is None:
        return None
    return value.value if isinstance(value, DealStatus) else str(value)


class LocalDealStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or store_path()
        self._lock = threading.Lock()
        self._deals: dict[str, DealPayload] = {}
        self._watchlists: dict[str, WatchlistFilter] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read local store %s: %s", self.path, exc)
            return

        for row in raw.get("deals", []):
            try:
                payload = DealPayload.model_validate(row)
                self._deals[payload.deal_id] = payload
            except Exception as exc:
                logger.warning("Skipping invalid deal in store: %s", exc)

        for row in raw.get("watchlists", []):
            try:
                item = WatchlistFilter.model_validate(row)
                self._watchlists[item.filter_id] = item
            except Exception as exc:
                logger.warning("Skipping invalid watchlist in store: %s", exc)

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "deals": [d.model_dump(mode="json") for d in self._deals.values()],
            "watchlists": [w.model_dump(mode="json") for w in self._watchlists.values()],
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        tmp.replace(self.path)

    def save_deal(self, payload: DealPayload) -> DealPayload:
        with self._lock:
            self._deals[payload.deal_id] = payload
            self._persist()
        return payload

    def get_deal(self, deal_id: str) -> Optional[DealPayload]:
        return self._deals.get(deal_id)

    def find_by_url(self, url: str) -> Optional[DealPayload]:
        normalized = url.strip().rstrip("/").lower()
        for deal in self._deals.values():
            if deal.url.rstrip("/").lower() == normalized:
                return deal
        return None

    def list_deals(
        self,
        tier: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[DealPayload]:
        rows = list(self._deals.values())
        if tier and tier != "all":
            wanted = tier.lower()
            rows = [d for d in rows if (_tier_value(d.deal_tier) or "").lower() == wanted]
        if status:
            wanted = status.lower()
            rows = [d for d in rows if (_status_value(d.status) or "").lower() == wanted]

        rows.sort(key=lambda d: (d.deal_score is not None, d.deal_score or 0), reverse=True)
        return rows[:limit]

    def save_watchlist(self, item: WatchlistFilter) -> WatchlistFilter:
        with self._lock:
            self._watchlists[item.filter_id] = item
            self._persist()
        return item

    def get_watchlist(self, filter_id: str) -> Optional[WatchlistFilter]:
        return self._watchlists.get(filter_id)

    def list_watchlists(self) -> list[WatchlistFilter]:
        return list(self._watchlists.values())

    def delete_watchlist(self, filter_id: str) -> bool:
        with self._lock:
            existed = filter_id in self._watchlists
            if existed:
                del self._watchlists[filter_id]
                self._persist()
        return existed

    def is_empty(self) -> bool:
        return not self._deals

    def pipeline_stats(self) -> dict:
        deals = list(self._deals.values())
        scores = [d.deal_score for d in deals if d.deal_score is not None]
        margins = [
            d.valuation_report.estimated_gross_margin
            for d in deals
            if d.valuation_report is not None
        ]
        tiers = [(_tier_value(d.deal_tier) or "").lower() for d in deals]
        return {
            "total_ingested": len(deals),
            "fire_deals": tiers.count("fire"),
            "strong_deals": tiers.count("strong"),
            "watchlist_deals": tiers.count("watchlist"),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "avg_margin": round(sum(margins) / len(margins), 4) if margins else 0,
        }


_store: Optional[LocalDealStore] = None


def get_local_store() -> LocalDealStore:
    global _store
    if _store is None:
        _store = LocalDealStore()
        if seed_demo_deals() and _store.is_empty():
            from backend.agents.local_pipeline import seed_catalog

            seed_catalog(_store)
    return _store


def reset_local_store(path: Optional[Path] = None, seed: bool = True) -> LocalDealStore:
    """Test helper — point the singleton at a fresh file."""
    global _store
    _store = LocalDealStore(path)
    if seed and seed_demo_deals() and _store.is_empty():
        from backend.agents.local_pipeline import seed_catalog

        seed_catalog(_store)
    return _store
