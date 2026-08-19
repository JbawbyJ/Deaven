"""
Heuristic deal pipeline for local development.

Produces Vision/Risk/Valuation reports and a composite score without
Anthropic, Playwright, Carfax, or live market APIs. Live agents can
replace this module when PIPELINE_MODE=full.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from backend.data.catalog import CATALOG, get_by_slug, get_by_url
from backend.agents.scoring import score_to_tier
from shared.schemas.deal import (
    ConditionGrade,
    DealPayload,
    DealSource,
    DealStatus,
    ListingData,
    RiskReport,
    ScoreComponents,
    ValuationReport,
    VisionReport,
    WatchlistFilter,
)

logger = logging.getLogger(__name__)

_YEAR_MAKE_MODEL_RE = re.compile(
    r"(\d{4})[-_ ]+([A-Za-z][\w-]+)[-_ ]+([A-Za-z0-9][\w-]+)",
)

SOURCE_HOSTS = (
    ("bringatrailer", DealSource.BRING_A_TRAILER),
    ("carsandbids", DealSource.CARS_AND_BIDS),
    ("ebay", DealSource.EBAY),
    ("classic.com", DealSource.CLASSIC_COM),
    ("tc-v.com", DealSource.TCV),
    ("facebook", DealSource.FACEBOOK),
    ("autotrader", DealSource.AUTOTRADER),
    ("hemmings", DealSource.HEMMINGS),
    ("craigslist", DealSource.CRAIGSLIST),
)


def detect_source(url: str) -> DealSource:
    host = urlparse(url).netloc.lower()
    path = url.lower()
    for token, source in SOURCE_HOSTS:
        if token in host or token in path:
            return source
    if url.lower().startswith("local://"):
        return DealSource.MANUAL
    return DealSource.MANUAL


def listing_from_catalog(item: dict[str, Any]) -> ListingData:
    return ListingData(
        title=item["title"],
        price=float(item["price"]),
        mileage=item.get("mileage"),
        year=item.get("year"),
        make=item.get("make"),
        model=item.get("model"),
        trim=item.get("trim"),
        location=item.get("location"),
        description=item.get("description"),
        seller_type=item.get("seller_type"),
        watch_count=item.get("watch_count"),
        bid_count=item.get("bid_count"),
        color_ext=item.get("color_ext"),
        color_int=item.get("color_int"),
        transmission=item.get("transmission"),
        drivetrain=item.get("drivetrain"),
        listing_date=datetime.now(timezone.utc),
    )


def payload_from_catalog(item: dict[str, Any]) -> DealPayload:
    return DealPayload(
        source=item.get("source", DealSource.MANUAL),
        url=item["url"],
        listing=listing_from_catalog(item),
        images=list(item.get("images") or []),
        status=DealStatus.INGESTED,
    )


def payload_from_url(url: str) -> DealPayload:
    """Resolve a URL to a DealPayload using the catalog, then URL parsing."""
    trimmed = url.strip()
    item = get_by_slug(trimmed) if trimmed.lower().startswith("local://") else get_by_url(trimmed)
    if item is None and trimmed.lower().startswith("local://"):
        item = get_by_slug(trimmed)
    if item is not None:
        return payload_from_catalog(item)

    source = detect_source(trimmed)
    year, make, model = _parse_ymm(trimmed)
    title = " ".join(str(p) for p in (year, make, model) if p) or "Manual listing"
    listing = ListingData(
        title=title,
        price=25000,
        year=year,
        make=make,
        model=model,
        location="Unknown",
        description=f"Local ingest of {trimmed}. Live scrape not configured.",
        seller_type="private",
        listing_date=datetime.now(timezone.utc),
    )
    return DealPayload(
        source=source,
        url=trimmed,
        listing=listing,
        flags=["local_heuristic_ingest"],
        status=DealStatus.INGESTED,
    )


def _parse_ymm(url: str) -> tuple[Optional[int], Optional[str], Optional[str]]:
    match = _YEAR_MAKE_MODEL_RE.search(url.replace("/", " "))
    if not match:
        return None, None, None
    return int(match.group(1)), match.group(2).title(), match.group(3).upper() if len(match.group(3)) <= 3 else match.group(3).title()


def _grade_from_score(score: float) -> ConditionGrade:
    if score >= 88:
        return ConditionGrade.A
    if score >= 75:
        return ConditionGrade.B
    if score >= 60:
        return ConditionGrade.C
    if score >= 40:
        return ConditionGrade.D
    return ConditionGrade.F


def _catalog_hints(payload: DealPayload) -> dict[str, Any]:
    item = get_by_url(payload.url) or get_by_slug(payload.url)
    return item or {}


def heuristic_vision(payload: DealPayload) -> VisionReport:
    hints = _catalog_hints(payload)
    score = float(hints.get("condition_hint") or 68.0)
    mileage = payload.listing.mileage or 80000
    if mileage > 120000:
        score -= 8
    elif mileage < 50000:
        score += 4
    score = max(0.0, min(100.0, score))
    flags = []
    if not payload.images:
        flags.append("photos_not_downloaded")
    if mileage > 100000:
        flags.append("high_mileage")
    return VisionReport(
        exterior_grade=_grade_from_score(score),
        interior_grade=_grade_from_score(max(0.0, score - 4)),
        flags=flags,
        condition_score=round(score, 1),
        photo_count=len(payload.images),
        confidence=0.55 if payload.images else 0.35,
        raw_analysis="Heuristic condition estimate from mileage, year, and catalog hints.",
    )


def heuristic_risk(payload: DealPayload) -> RiskReport:
    hints = _catalog_hints(payload)
    score = float(hints.get("provenance_hint") or 65.0)
    title_lower = payload.listing.title.lower()
    flags: list[str] = []
    auto_disqualify = False
    reason = None
    for token, label in (
        ("salvage", "Salvage title — auto-disqualified"),
        ("flood", "Flood damage reported — auto-disqualified"),
        ("parts only", "Parts-only listing — auto-disqualified"),
    ):
        if token in title_lower:
            flags.append(token.replace(" ", "_"))
            auto_disqualify = True
            reason = label
            score = 0
    if payload.listing.seller_type == "dealer":
        score += 2
    return RiskReport(
        owner_count=1 if hints else None,
        accident_count=0,
        title_clean=not flags,
        title_flags=flags,
        recall_count=0,
        open_recalls=[],
        service_record_completeness=0.6 if hints else 0.4,
        provenance_score=max(0.0, min(100.0, score)),
        auto_disqualify=auto_disqualify,
        disqualify_reason=reason,
    )


def _price_score(price_vs_comp_pct: float) -> float:
    if price_vs_comp_pct <= -0.20:
        return 95
    if price_vs_comp_pct <= -0.10:
        return 80
    if price_vs_comp_pct <= 0.00:
        return 60
    if price_vs_comp_pct <= 0.05:
        return 35
    return 10


def _margin_score(gross_margin: float) -> float:
    if gross_margin >= 0.25:
        return 95
    if gross_margin >= 0.15:
        return 78
    if gross_margin >= 0.10:
        return 60
    if gross_margin >= 0.05:
        return 35
    return 10


def heuristic_valuation(payload: DealPayload, vision: VisionReport) -> ValuationReport:
    hints = _catalog_hints(payload)
    price = payload.listing.price
    market = float(hints.get("market_avg") or price * 1.05)
    price_vs = (price - market) / market if market else 0.0
    retail = market * 1.10
    recon = 1500 if vision.condition_score >= 70 else 4000
    transport = 900 if (payload.listing.location or "").upper() != "JAPAN" else 1800
    total_cost = price + recon + transport
    margin = (retail - total_cost) / retail if retail else 0.0
    demand = float(hints.get("demand_hint") or 55.0)
    if payload.listing.watch_count and payload.listing.watch_count > 100:
        demand = min(100.0, demand + 6)
    return ValuationReport(
        comp_avg=round(market, 2),
        comp_low=round(market * 0.88, 2),
        comp_high=round(market * 1.12, 2),
        comp_sample_size=8 if hints else 0,
        price_vs_comp_pct=round(price_vs, 4),
        estimated_retail=round(retail, 2),
        estimated_recon=float(recon),
        estimated_transport=float(transport),
        estimated_gross_margin=round(margin, 4),
        days_to_sell_avg=35 if demand >= 75 else 50,
        demand_score=round(min(100.0, demand), 1),
        price_score=_price_score(price_vs),
        margin_score=_margin_score(margin),
    )


def _narrative(payload: DealPayload) -> str:
    listing = payload.listing
    ymm = " ".join(str(p) for p in (listing.year, listing.make, listing.model) if p) or listing.title
    val = payload.valuation_report
    vs = f"{val.price_vs_comp_pct * 100:+.1f}% vs comps" if val else "no comps"
    risk = "none flagged"
    if payload.risk_report and payload.risk_report.title_flags:
        risk = ", ".join(payload.risk_report.title_flags)
    elif payload.vision_report and payload.vision_report.flags:
        risk = ", ".join(payload.vision_report.flags)
    tier = (
        payload.deal_tier.value
        if hasattr(payload.deal_tier, "value")
        else str(payload.deal_tier)
    )
    action = {
        "fire": "Move now: confirm title, schedule PPI, draft outreach.",
        "strong": "Shortlist it — verify service history before bidding.",
        "watchlist": "Park it on the watchlist and wait for a price move.",
        "pass": "Pass unless the seller drops closer to market.",
        "discard": "Discard — does not clear the bar.",
    }.get(tier.lower(), "Review manually.")
    return (
        f"{tier.upper()} — {ymm} at ${listing.price:,.0f} ({vs}). "
        f"Primary risk: {risk}. {action}"
    )


def score_payload(payload: DealPayload) -> DealPayload:
    """Fill agent reports + composite score in place."""
    payload.vision_report = heuristic_vision(payload)
    payload.risk_report = heuristic_risk(payload)

    if payload.risk_report.auto_disqualify:
        payload.deal_score = 0.0
        payload.deal_tier = score_to_tier(0)
        payload.narrative = f"Auto-disqualified: {payload.risk_report.disqualify_reason}"
        payload.status = DealStatus.DISCARDED
        payload.flags.append("auto_disqualified")
        return payload

    payload.valuation_report = heuristic_valuation(payload, payload.vision_report)
    components = ScoreComponents(
        price_score=payload.valuation_report.price_score,
        provenance_score=payload.risk_report.provenance_score,
        demand_score=payload.valuation_report.demand_score,
        condition_score=payload.vision_report.condition_score,
        margin_score=payload.valuation_report.margin_score,
    )
    payload.score_components = components
    payload.deal_score = components.compute()
    payload.deal_tier = score_to_tier(payload.deal_score)
    payload.narrative = _narrative(payload)
    payload.status = DealStatus.SCORED
    payload.flags = [f for f in payload.flags if f != "local_heuristic_ingest"]
    payload.flags.append("scored_local_heuristic")
    return payload


def ingest_url(url: str) -> DealPayload:
    return score_payload(payload_from_url(url))


def scout_catalog(filters: Optional[WatchlistFilter] = None) -> list[DealPayload]:
    """Return scored catalog listings, optionally filtered."""
    rows = []
    for item in CATALOG:
        if filters is not None:
            from backend.data.catalog import match_filters

            if not match_filters(item, filters):
                continue
        rows.append(score_payload(payload_from_catalog(item)))
    return rows


def seed_catalog(store) -> None:
    """Populate an empty store with the scored catalog + a sample watchlist."""
    for payload in scout_catalog():
        store.save_deal(payload)
    store.save_watchlist(
        WatchlistFilter(
            name="E46 M3 Hunt",
            makes=["BMW"],
            models=["M3"],
            year_min=2001,
            year_max=2006,
            price_min=15_000,
            price_max=60_000,
        )
    )
    logger.info("Seeded local store with %d catalog deals", len(CATALOG))
