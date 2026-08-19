"""
backend/agents/valuation.py
Valuation Agent — pulls market comps, models margin, scores demand.
Returns ValuationReport feeding into Price, Demand, and Margin score dimensions.
"""

from __future__ import annotations
import logging
from typing import Optional

import httpx

from shared.schemas.deal import DealPayload, ValuationReport

from backend.agents.scrapers.bat import BaTScraper
from backend.agents.scrapers.classic_com import ClassicComCompClient

logger = logging.getLogger(__name__)


# ─── Comp Sources ─────────────────────────────────────────────────────────────


class MarketCompAggregator:
    """
    Aggregates comps across sources and normalizes to a single dataset.
    Adjusts for mileage using a simple depreciation curve.
    """

    MILEAGE_DEPRECIATION_PER_10K = 0.015   # 1.5% value reduction per 10k miles

    def __init__(self):
        self.bat = BaTScraper()
        self.classic_com = ClassicComCompClient()

    async def get_comps(
        self,
        make:    str,
        model:   str,
        year:    int,
        mileage: Optional[int] = None,
    ) -> list[float]:
        """Returns list of adjusted comp prices."""

        year_min = year - 1
        year_max = year + 1

        raw_comps = await self.classic_com.get_sold_comps(make, model, year_min, year_max)

        if not raw_comps:
            # If Classic.com returns nothing (Cloudflare block etc), fall back to BaT
            raw_comps = await self.bat.get_sold_comps(make, model, year_min, year_max)

        # Adjust for mileage variance
        adjusted = []
        for comp in raw_comps:
            comp_price   = float(comp.get("price", 0))
            comp_mileage = comp.get("mileage")
            if mileage and comp_mileage and comp_price > 0:
                mileage_diff = (mileage - comp_mileage) / 10_000
                adjustment   = 1 - (mileage_diff * self.MILEAGE_DEPRECIATION_PER_10K)
                comp_price   = comp_price * max(0.5, adjustment)
            if comp_price > 0:
                adjusted.append(comp_price)

        return adjusted

    def summarize(self, comps: list[float]) -> dict:
        if not comps:
            return {"avg": 0, "low": 0, "high": 0, "count": 0}
        import statistics
        return {
            "avg":   round(statistics.mean(comps), 2),
            "low":   round(min(comps), 2),
            "high":  round(max(comps), 2),
            "count": len(comps),
        }


# ─── Demand Scorer ────────────────────────────────────────────────────────────

class DemandScorer:
    """
    Scores vehicle demand using multiple signals.
    Higher = more liquid, faster to sell.
    """

    # Historical average days-to-sell by model segment
    # Populated from deal outcome data over time
    DAYS_TO_SELL_DEFAULTS = {
        "porsche":    28,
        "bmw m":      35,
        "toyota supra": 21,
        "mazda rx-7": 30,
        "land rover": 55,
        "ferrari":    45,
        "default":    45,
    }

    async def score(
        self,
        make:        str,
        model:       str,
        watch_count: Optional[int],
        listing_age_days: int = 0,
    ) -> tuple[float, int]:
        """Returns (demand_score 0-100, days_to_sell_estimate)."""

        score = 50.0   # base

        # Watch count signal
        if watch_count:
            if watch_count > 200:   score += 30
            elif watch_count > 100: score += 20
            elif watch_count > 50:  score += 12
            elif watch_count > 20:  score += 6

        # Listing age signal — longer on market = weaker demand
        if listing_age_days > 60:   score -= 20
        elif listing_age_days > 30: score -= 10
        elif listing_age_days > 14: score -= 5

        # Days to sell estimate
        model_key = next(
            (k for k in self.DAYS_TO_SELL_DEFAULTS if k in f"{make} {model}".lower()),
            "default"
        )
        days_to_sell = self.DAYS_TO_SELL_DEFAULTS[model_key]

        return round(min(100, max(0, score)), 1), days_to_sell


# ─── Cost Estimator ───────────────────────────────────────────────────────────

class CostEstimator:
    """
    Estimates acquisition costs beyond purchase price.
    Feeds margin modeling.
    """

    # Regional transport cost per mile estimate
    TRANSPORT_COST_PER_MILE = 1.10

    def estimate_transport(self, origin_state: Optional[str], destination_state: str = "NJ") -> float:
        """Rough transport estimate based on region."""
        if not origin_state:
            return 1_200   # default national estimate

        local_states = {"NJ", "NY", "CT", "PA", "DE", "MD"}
        mid_states   = {"VA", "NC", "SC", "GA", "FL", "MA", "VT", "NH", "ME"}

        if origin_state.upper() in local_states:  return 400
        if origin_state.upper() in mid_states:    return 900
        return 1_500   # cross-country default

    def estimate_recon(self, condition_score: float) -> float:
        """Estimate reconditioning cost from condition score."""
        if condition_score >= 85:   return 500
        if condition_score >= 70:   return 1_500
        if condition_score >= 55:   return 3_500
        if condition_score >= 40:   return 7_000
        return 15_000


# ─── Score Calculators ────────────────────────────────────────────────────────

def calc_price_score(price_vs_comp_pct: float) -> float:
    """Price score from percentage below/above market comp."""
    if   price_vs_comp_pct <= -0.20:  return 95
    elif price_vs_comp_pct <= -0.10:  return 80
    elif price_vs_comp_pct <=  0.00:  return 60
    elif price_vs_comp_pct <=  0.05:  return 35
    else:                              return 10

def calc_margin_score(gross_margin: float) -> float:
    """Margin score from estimated gross margin decimal."""
    if   gross_margin >= 0.25:  return 95
    elif gross_margin >= 0.15:  return 78
    elif gross_margin >= 0.10:  return 60
    elif gross_margin >= 0.05:  return 35
    else:                        return 10


# ─── Valuation Agent ──────────────────────────────────────────────────────────

class ValuationAgent:

    def __init__(self):
        self.comps   = MarketCompAggregator()
        self.demand  = DemandScorer()
        self.costs   = CostEstimator()

    async def run(self, payload: DealPayload) -> ValuationReport:
        listing = payload.listing

        make    = listing.make    or "unknown"
        model   = listing.model   or "unknown"
        year    = listing.year    or 2000
        price   = listing.price
        mileage = listing.mileage
        location = listing.location

        # 1. Pull comps
        comp_prices = await self.comps.get_comps(make, model, year, mileage)
        comp_summary = self.comps.summarize(comp_prices)
        comp_avg = comp_summary["avg"]

        # 2. Price vs comp
        if comp_avg > 0:
            price_vs_comp_pct = (price - comp_avg) / comp_avg
            estimated_retail  = comp_avg * 1.10   # target 10% above market avg
        else:
            # No comp data — use listing price as proxy, flag it
            price_vs_comp_pct = 0.0
            estimated_retail  = price * 1.15
            logger.warning(f"[{payload.deal_id}] No comp data for {year} {make} {model}")

        # 3. Cost estimates
        origin_state = _extract_state(location)
        condition_score = (
            payload.vision_report.condition_score
            if payload.vision_report else 60.0
        )
        transport = self.costs.estimate_transport(origin_state)
        recon     = self.costs.estimate_recon(condition_score)

        # 4. Gross margin
        total_cost     = price + transport + recon
        gross_margin   = (estimated_retail - total_cost) / estimated_retail if estimated_retail > 0 else 0

        # 5. Demand score
        listing_age = _calc_listing_age(listing)
        demand_score, days_to_sell = await self.demand.score(
            make, model, listing.watch_count, listing_age
        )

        # 6. Sub-scores
        price_score  = calc_price_score(price_vs_comp_pct)
        margin_score = calc_margin_score(gross_margin)

        report = ValuationReport(
            comp_avg               = comp_avg or price,
            comp_low               = comp_summary["low"] or price * 0.85,
            comp_high              = comp_summary["high"] or price * 1.15,
            comp_sample_size       = comp_summary["count"],
            price_vs_comp_pct      = round(price_vs_comp_pct, 4),
            estimated_retail       = round(estimated_retail, 2),
            estimated_recon        = round(recon, 2),
            estimated_transport    = round(transport, 2),
            estimated_gross_margin = round(gross_margin, 4),
            days_to_sell_avg       = days_to_sell,
            demand_score           = demand_score,
            price_score            = price_score,
            margin_score           = margin_score,
        )

        logger.info(
            f"[{payload.deal_id}] Valuation: price_score={price_score} "
            f"margin={gross_margin:.1%} demand={demand_score}"
        )
        return report


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_state(location: Optional[str]) -> Optional[str]:
    """Best-effort state extraction from location string."""
    if not location:
        return None
    parts = location.replace(",", " ").split()
    # Look for 2-letter uppercase state code
    for part in reversed(parts):
        if len(part) == 2 and part.isupper():
            return part
    return None

def _calc_listing_age(listing) -> int:
    """Days since listing was posted."""
    from datetime import datetime, timezone
    if not listing.listing_date:
        return 0
    now = datetime.now(timezone.utc)
    listed = listing.listing_date
    if listed.tzinfo is None:
        listed = listed.replace(tzinfo=timezone.utc)
    return (now - listed).days
