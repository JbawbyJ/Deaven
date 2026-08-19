"""
backend/core/orchestrator.py
Deal Orchestrator — LangGraph graph wiring Scout → Triage → [Vision | Risk | Valuation] 
→ Scoring → Outreach → Dashboard Event.

Agents run concurrently where possible. State flows as DealPayload.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Literal, Optional

from langgraph.graph import StateGraph, END

from shared.schemas.deal import DealPayload, DealStatus, DealTier, WatchlistFilter
from backend.agents.scout     import ScoutAgent
from backend.agents.vision    import VisionAgent
from backend.agents.risk      import RiskAgent
from backend.agents.valuation import ValuationAgent
from backend.agents.scoring   import ScoringEngine
from backend.db.client        import save_deal

logger = logging.getLogger(__name__)


# ─── Node Functions ───────────────────────────────────────────────────────────
# Each node receives DealPayload, returns updated DealPayload.
# LangGraph passes state between nodes automatically.

async def triage_node(payload: DealPayload) -> DealPayload:
    """
    Fast rule-based filter. Kills obviously bad listings before
    spinning up Vision/Risk/Valuation agents.
    """
    listing = payload.listing
    flags   = []

    # Minimum photo check
    if len(payload.images) < 3:
        flags.append("insufficient_photos")

    # Price sanity check
    if listing.price <= 0:
        flags.append("invalid_price")
        payload.status = DealStatus.DISCARDED
        return payload

    # Title keyword hard-stops
    title_lower = listing.title.lower()
    hard_stop_keywords = ["salvage", "parts only", "flood", "needs engine", "as-is no title"]
    for kw in hard_stop_keywords:
        if kw in title_lower:
            flags.append(f"title_keyword_{kw.replace(' ', '_')}")
            payload.status = DealStatus.DISCARDED
            return payload

    payload.flags.extend(flags)
    payload.status = DealStatus.TRIAGED
    logger.debug(f"[{payload.deal_id}] Triage passed. Flags: {flags}")
    return payload


async def parallel_agents_node(payload: DealPayload) -> DealPayload:
    """
    Runs Vision, Risk, and Valuation agents concurrently.
    All three are independent — no reason to serialize.
    """
    payload.status = DealStatus.SCORING

    vision_agent    = VisionAgent()
    risk_agent      = RiskAgent()
    valuation_agent = ValuationAgent()

    try:
        vision, risk, valuation = await asyncio.gather(
            vision_agent.run(payload),
            risk_agent.run(payload),
            valuation_agent.run(payload),
            return_exceptions=True,
        )
    except Exception as e:
        logger.error(f"[{payload.deal_id}] Parallel agents fatal error: {e}")
        payload.errors.append(f"parallel_agents_failed: {e}")
        return payload

    # Handle individual agent failures gracefully
    if isinstance(vision, Exception):
        logger.error(f"[{payload.deal_id}] Vision agent failed: {vision}")
        payload.errors.append(f"vision_failed: {vision}")
        from shared.schemas.deal import VisionReport
        vision = VisionReport.degraded()

    if isinstance(risk, Exception):
        logger.error(f"[{payload.deal_id}] Risk agent failed: {risk}")
        payload.errors.append(f"risk_failed: {risk}")
        from shared.schemas.deal import RiskReport
        risk = RiskReport.degraded()

    if isinstance(valuation, Exception):
        logger.error(f"[{payload.deal_id}] Valuation agent failed: {valuation}")
        payload.errors.append(f"valuation_failed: {valuation}")
        # Valuation failure is more critical — flag for manual review
        payload.flags.append("valuation_failed_manual_review")

    payload.vision_report    = vision    if not isinstance(vision, Exception)    else None
    payload.risk_report      = risk      if not isinstance(risk, Exception)      else None
    payload.valuation_report = valuation if not isinstance(valuation, Exception) else None

    return payload


async def scoring_node(payload: DealPayload) -> DealPayload:
    """Runs scoring engine. Computes composite score and narrative."""
    engine = ScoringEngine()
    payload = await engine.run(payload)
    payload.status = DealStatus.SCORED
    return payload


async def outreach_node(payload: DealPayload) -> DealPayload:
    """
    Drafts seller outreach for Fire/Strong deals.
    Human reviews before send.
    """
    from shared.schemas.deal import OutreachDraft
    listing = payload.listing

    subject = f"Interested in your {listing.year} {listing.make} {listing.model}"
    body = (
        f"Hi,\n\n"
        f"I came across your listing for the {listing.year} {listing.make} {listing.model} "
        f"and I'm very interested. I'm a professional buyer specializing in quality vehicles "
        f"like this one.\n\n"
        f"Would you be open to discussing a quick, straightforward transaction? "
        f"I can arrange transport and handle all paperwork.\n\n"
        f"Best regards"
    )

    payload.outreach_draft = OutreachDraft(
        subject = subject,
        body    = body,
        channel = "email",
        status  = "pending_review",
    )
    payload.status = DealStatus.ACTIONED
    logger.info(f"[{payload.deal_id}] Outreach draft created")
    return payload


async def discard_node(payload: DealPayload) -> DealPayload:
    payload.status = DealStatus.DISCARDED
    logger.debug(f"[{payload.deal_id}] Discarded. Reason: {payload.flags}")
    return payload


async def dashboard_event_node(payload: DealPayload) -> DealPayload:
    """
    Pushes deal to dashboard feed and fires alerts if score warrants.
    """
    logger.info(
        f"[DASHBOARD] New deal: {payload.deal_score} ({payload.deal_tier}) — "
        f"{payload.listing.year} {payload.listing.make} {payload.listing.model} "
        f"@ ${payload.listing.price:,.0f}"
    )
    save_deal(payload)
    # TODO: if tier in [FIRE, STRONG]: send_alert(payload)
    return payload


# ─── Routing Functions ────────────────────────────────────────────────────────

def route_triage(payload: DealPayload) -> Literal["continue", "discard"]:
    if payload.status == DealStatus.DISCARDED:
        return "discard"
    return "continue"

def route_risk(payload: DealPayload) -> Literal["continue", "discard"]:
    if payload.risk_report and payload.risk_report.auto_disqualify:
        return "discard"
    return "continue"

def route_score(payload: DealPayload) -> Literal["outreach", "watchlist", "pass", "discard"]:
    tier = payload.deal_tier
    if tier in [DealTier.FIRE, DealTier.STRONG]:
        return "outreach"
    if tier == DealTier.WATCHLIST:
        return "watchlist"
    if tier == DealTier.PASS:
        return "pass"
    return "discard"


# ─── Graph Builder ────────────────────────────────────────────────────────────

def build_deal_graph():
    """
    Constructs and compiles the LangGraph deal pipeline.
    Returns a compiled graph ready to invoke with a DealPayload.
    """
    graph = StateGraph(DealPayload)

    # Register nodes
    graph.add_node("triage",           triage_node)
    graph.add_node("parallel_agents",  parallel_agents_node)
    graph.add_node("scoring",          scoring_node)
    graph.add_node("outreach",         outreach_node)
    graph.add_node("dashboard_event",  dashboard_event_node)
    graph.add_node("discard",          discard_node)

    # Entry point
    graph.set_entry_point("triage")

    # Triage → continue or discard
    graph.add_conditional_edges("triage", route_triage, {
        "continue": "parallel_agents",
        "discard":  "discard",
    })

    # All parallel agents feed into scoring
    graph.add_edge("parallel_agents", "scoring")

    # Scoring → route by tier
    graph.add_conditional_edges("scoring", route_score, {
        "outreach":  "outreach",
        "watchlist": "dashboard_event",   # save to DB, no outreach
        "pass":      "dashboard_event",   # save for comp data
        "discard":   "discard",
    })

    # Outreach → dashboard event
    graph.add_edge("outreach", "dashboard_event")

    # Terminal nodes
    graph.add_edge("dashboard_event", END)
    graph.add_edge("discard",         END)

    return graph.compile()


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class DealOrchestrator:
    """
    Main orchestration controller.
    Runs the deal graph for individual payloads or batches from Scout.
    """

    def __init__(self):
        self.graph = build_deal_graph()
        self.scout = ScoutAgent()

    async def process_deal(self, payload: DealPayload) -> DealPayload:
        """Run a single DealPayload through the full pipeline."""
        try:
            result = await self.graph.ainvoke(payload)
            return result
        except Exception as e:
            logger.error(f"[{payload.deal_id}] Pipeline error: {e}")
            payload.errors.append(str(e))
            return payload

    async def process_batch(self, payloads: list[DealPayload]) -> list[DealPayload]:
        """
        Process a batch of payloads concurrently.
        Limits concurrency to avoid hammering APIs.
        """
        semaphore = asyncio.Semaphore(5)   # max 5 deals in-flight at once

        async def run_with_limit(p: DealPayload) -> DealPayload:
            async with semaphore:
                return await self.process_deal(p)

        results = await asyncio.gather(*[run_with_limit(p) for p in payloads])
        return list(results)

    async def run_scout_cycle(self, filters: WatchlistFilter) -> list[DealPayload]:
        """
        Full cycle: Scout → batch pipeline.
        Called by the scheduler every N minutes.
        """
        logger.info(f"Scout cycle starting for filter: {filters.name}")
        new_listings = await self.scout.run(filters)

        if not new_listings:
            logger.info("Scout cycle: no new listings found")
            return []

        logger.info(f"Scout cycle: {len(new_listings)} new listings → pipeline")
        results = await self.process_batch(new_listings)

        # Summary log
        tiers = {}
        for r in results:
            tiers[r.deal_tier] = tiers.get(r.deal_tier, 0) + 1
        logger.info(f"Scout cycle complete. Results: {tiers}")

        return results


# ─── Scheduler ────────────────────────────────────────────────────────────────

async def run_scheduler(filters: list[WatchlistFilter], interval_seconds: int = 900):
    """
    Runs scout cycles on a schedule.
    Default: every 15 minutes (900s).
    Production: replace with APScheduler or Celery Beat.
    """
    orchestrator = DealOrchestrator()
    logger.info(f"Scheduler started. Interval: {interval_seconds}s, Filters: {len(filters)}")

    while True:
        for f in filters:
            try:
                await orchestrator.run_scout_cycle(f)
            except Exception as e:
                logger.error(f"Scout cycle failed for '{f.name}': {e}")
        await asyncio.sleep(interval_seconds)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    from shared.schemas.deal import DealSource

    # Example: watch for E46 M3s
    example_filter = WatchlistFilter(
        name      = "E46 M3",
        makes     = ["BMW"],
        models    = ["M3"],
        year_min  = 2001,
        year_max  = 2006,
        price_min = 15_000,
        price_max = 60_000,
        sources   = [DealSource.BRING_A_TRAILER, DealSource.EBAY],
    )

    asyncio.run(run_scheduler([example_filter], interval_seconds=900))
