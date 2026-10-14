"""
Price observations for one listing, stored in a JSON file beside the deal store.

Summary math lives in summarize_history. PriceHistoryStore only reads and writes.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.core.settings import data_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceObservation:
    listing_id: str
    price: float
    observed_at: datetime


@dataclass(frozen=True)
class PriceHistorySummary:
    listing_id: str
    current_price: float | None
    first_price: float | None
    total_drop_amount: float | None
    total_drop_pct: float | None
    last_drop_amount: float | None
    last_drop_pct: float | None
    change_count: int
    days_on_market: int | None
    trend: str


def summarize_history(
    listing_id: str,
    observations: list[PriceObservation],
    *,
    as_of: datetime | None = None,
) -> PriceHistorySummary:
    """Current and first price, net drop, latest drop, changes, days, and trend.

    Drop percents are fractions of the earlier price (0.10 is 10%). Days on
    market run from the first observation to as_of, or to the last observation
    when as_of is omitted. Trend compares the current price with the first.
    """
    ordered = sorted(observations, key=lambda row: row.observed_at)
    if not ordered:
        return PriceHistorySummary(
            listing_id=listing_id,
            current_price=None,
            first_price=None,
            total_drop_amount=None,
            total_drop_pct=None,
            last_drop_amount=None,
            last_drop_pct=None,
            change_count=0,
            days_on_market=None,
            trend="unknown",
        )

    first = ordered[0].price
    current = ordered[-1].price
    total_amount = round(max(0.0, first - current), 2)
    total_pct = round(total_amount / first, 4) if first > 0 else None
    last_amount = None
    last_pct = None
    changes = 0
    for previous, nxt in zip(ordered, ordered[1:]):
        if nxt.price != previous.price:
            changes += 1
        if nxt.price < previous.price:
            last_amount = round(previous.price - nxt.price, 2)
            last_pct = round(last_amount / previous.price, 4) if previous.price > 0 else None

    end = _as_utc(as_of) if as_of is not None else ordered[-1].observed_at
    if current < first:
        trend = "down"
    elif current > first:
        trend = "up"
    else:
        trend = "flat"
    return PriceHistorySummary(
        listing_id=listing_id,
        current_price=current,
        first_price=first,
        total_drop_amount=total_amount,
        total_drop_pct=total_pct,
        last_drop_amount=last_amount,
        last_drop_pct=last_pct,
        change_count=changes,
        days_on_market=max(0, (end - ordered[0].observed_at).days),
        trend=trend,
    )


class PriceHistoryStore:
    """JSON file in the same data directory as local_store.json."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (data_dir() / "price_history.json")
        self._lock = threading.Lock()
        self._rows: dict[str, list[PriceObservation]] = {}
        self._load()

    def record(self, listing_id: str, price: float, observed_at: datetime) -> list[PriceObservation]:
        listing_id = listing_id.strip()
        if not listing_id:
            raise ValueError("listing_id is required")
        if price < 0:
            raise ValueError("price must be non-negative")
        point = PriceObservation(listing_id, round(float(price), 2), _as_utc(observed_at))
        with self._lock:
            rows = [row for row in self._rows.get(listing_id, []) if row.observed_at != point.observed_at]
            rows.append(point)
            rows.sort(key=lambda row: row.observed_at)
            self._rows[listing_id] = rows
            self._persist()
            return list(rows)

    def observations(self, listing_id: str) -> list[PriceObservation]:
        return list(self._rows.get(listing_id, []))

    def summary(self, listing_id: str, *, as_of: datetime | None = None) -> PriceHistorySummary:
        return summarize_history(listing_id, self.observations(listing_id), as_of=as_of)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read price history %s: %s", self.path, exc)
            return
        loaded: dict[str, list[PriceObservation]] = {}
        for listing_id, rows in (raw.get("observations") or {}).items():
            points = []
            for row in rows:
                try:
                    points.append(
                        PriceObservation(
                            listing_id=str(listing_id),
                            price=float(row["price"]),
                            observed_at=_as_utc(datetime.fromisoformat(row["observed_at"])),
                        )
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    logger.warning("Skipping invalid price observation: %s", exc)
            points.sort(key=lambda row: row.observed_at)
            if points:
                loaded[str(listing_id)] = points
        self._rows = loaded

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "observations": {
                listing_id: [
                    {"price": row.price, "observed_at": row.observed_at.isoformat()}
                    for row in rows
                ]
                for listing_id, rows in self._rows.items()
            }
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self.path)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
