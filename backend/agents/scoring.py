"""
backend/agents/scoring.py
Scoring Engine — assembles agent reports into a composite Deal Score
and generates an LLM narrative explaining the score.
"""

from __future__ import annotations
import logging
import os
from typing import Optional

from shared.schemas.deal import (
    DealPayload, DealTier, ScoreComponents,
    RiskReport, ValuationReport, VisionReport,
)

logger = logging.getLogger(__name__)


# ─── Tier Thresholds ──────────────────────────────────────────────────────────

TIER_THRESHOLDS = [
    (85, DealTier.FIRE),
    (70, DealTier.STRONG),
    (55, DealTier.WATCHLIST),
    (40, DealTier.PASS),
    (0,  DealTier.DISCARD),
]

def score_to_tier(score: float) -> DealTier:
    for threshold, tier in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return DealTier.DISCARD


# ─── Narrative Prompt ─────────────────────────────────────────────────────────

NARRATIVE_SYSTEM = """You are a deal advisor for a boutique automotive dealership specializing in 
niche and collector vehicles. Write concise, direct deal summaries — no fluff.
Respond in 2-3 sentences max. Lead with the score tier and key reason, then 
highlight the biggest risk or opportunity, then give a concrete next action."""

def build_narrative_prompt(payload: DealPayload) -> str:
    l  = payload.listing
    sc = payload.score_components
    vr = payload.vision_report
    rr = payload.risk_report
    val = payload.valuation_report

    return f"""
Deal: {l.year} {l.make} {l.model} — ${l.price:,.0f} — {l.mileage or 'N/A'} miles
Source: {payload.source} | Score: {payload.deal_score} ({payload.deal_tier})

Score breakdown:
- Price:      {sc.price_score:.0f}/100 ({val.price_vs_comp_pct*100:+.1f}% vs comp avg ${val.comp_avg:,.0f})
- Provenance: {sc.provenance_score:.0f}/100 (owners: {rr.owner_count or 'unknown'}, accidents: {rr.accident_count or 0})
- Demand:     {sc.demand_score:.0f}/100 (avg {val.days_to_sell_avg}d to sell)
- Condition:  {sc.condition_score:.0f}/100 (ext: {vr.exterior_grade}, int: {vr.interior_grade})
- Margin:     {sc.margin_score:.0f}/100 ({val.estimated_gross_margin*100:.1f}% est. gross)

Flags: {', '.join((rr.title_flags or []) + (vr.flags or [])) or 'none'}
Est. all-in cost: ${l.price + val.estimated_transport + val.estimated_recon:,.0f}
Est. retail: ${val.estimated_retail:,.0f}

Write a 2-3 sentence deal advisory note.
"""


# ─── Scoring Engine ───────────────────────────────────────────────────────────

class ScoringEngine:
    """
    Assembles VisionReport + RiskReport + ValuationReport into a Deal Score.
    Generates LLM narrative. Returns updated DealPayload.
    """

    def __init__(self, anthropic_client=None):
        self.client = anthropic_client
        if self.client is None and os.getenv("ANTHROPIC_API_KEY"):
            try:
                import anthropic

                self.client = anthropic.AsyncAnthropic()
            except Exception as exc:
                logger.warning("Anthropic client unavailable, using template narratives: %s", exc)

    async def run(self, payload: DealPayload) -> DealPayload:
        """Main entry. Mutates and returns payload with score + narrative."""

        # Guard: auto-disqualify takes priority
        if payload.risk_report and payload.risk_report.auto_disqualify:
            payload.deal_score = 0.0
            payload.deal_tier  = DealTier.DISCARD
            payload.narrative  = f"Auto-disqualified: {payload.risk_report.disqualify_reason}"
            return payload

        # 1. Extract sub-scores from agent reports
        components = self._extract_components(payload)
        payload.score_components = components

        # 2. Compute weighted composite
        raw_score = components.compute()

        # 3. Apply dynamic adjustments
        adjusted_score = self._apply_dynamic_adjustments(raw_score, payload)

        # 4. Clamp and tier
        payload.deal_score = round(min(100, max(0, adjusted_score)), 1)
        payload.deal_tier  = score_to_tier(payload.deal_score)

        # 5. Generate narrative
        payload.narrative = await self._generate_narrative(payload)

        logger.info(
            f"[{payload.deal_id}] Score: {payload.deal_score} → {payload.deal_tier} "
            f"| {payload.listing.year} {payload.listing.make} {payload.listing.model}"
        )
        return payload

    def _extract_components(self, payload: DealPayload) -> ScoreComponents:
        vr  = payload.vision_report
        rr  = payload.risk_report
        val = payload.valuation_report

        # Fallback to neutral 50 if an agent report is missing
        condition_score  = vr.condition_score   if vr  else 50.0
        provenance_score = rr.provenance_score  if rr  else 50.0
        price_score      = val.price_score      if val else 50.0
        demand_score     = val.demand_score     if val else 50.0
        margin_score     = val.margin_score     if val else 50.0

        return ScoreComponents(
            price_score      = price_score,
            provenance_score = provenance_score,
            demand_score     = demand_score,
            condition_score  = condition_score,
            margin_score     = margin_score,
        )

    def _apply_dynamic_adjustments(self, score: float, payload: DealPayload) -> float:
        """Time-based and signal-based score adjustments."""
        adjustments = 0.0
        listing = payload.listing

        # Price drop detected (motivated seller signal)
        if getattr(listing, "price_drop_count", 0) and listing.price_drop_count > 0:
            adjustments += 8
            logger.debug(f"[{payload.deal_id}] +8 price drop detected")

        # Watch count velocity (competition signal — move faster, but also validates demand)
        if listing.watch_count and listing.watch_count > 100:
            adjustments += 5

        # Stale listing penalty (> 30 days no price drop)
        from datetime import datetime, timezone
        if listing.listing_date:
            listed = listing.listing_date
            if listed.tzinfo is None:
                listed = listed.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - listed).days
            if age_days > 60 and getattr(listing, "price_drop_count", 0) == 0:
                adjustments -= 8
            elif age_days > 30 and getattr(listing, "price_drop_count", 0) == 0:
                adjustments -= 4

        # Vision confidence penalty — if we couldn't see the car well, penalize
        if payload.vision_report and payload.vision_report.confidence < 0.4:
            adjustments -= 5

        return score + adjustments

    async def _generate_narrative(self, payload: DealPayload) -> str:
        """Generate LLM deal advisory narrative."""
        if not all([payload.vision_report, payload.risk_report, payload.valuation_report]):
            return f"Score: {payload.deal_score} ({payload.deal_tier}). Some agent data missing — manual review recommended."

        if self.client is None:
            return (
                f"Score: {payload.deal_score} ({payload.deal_tier}). "
                "Template narrative — set ANTHROPIC_API_KEY for LLM write-ups."
            )

        try:
            prompt = build_narrative_prompt(payload)
            response = await self.client.messages.create(
                model      = "claude-haiku-4-5-20251001",
                max_tokens = 200,
                system     = NARRATIVE_SYSTEM,
                messages   = [{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Narrative generation failed: {e}")
            return f"Score: {payload.deal_score} ({payload.deal_tier}). Narrative generation failed."
