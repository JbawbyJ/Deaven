"""
backend/api/main.py
FastAPI application — REST API for the Deaven dashboard.

Contract matches `Deaven API - Swagger UI.pdf`:
  GET  /health
  POST /deals/ingest
  GET  /deals
  GET  /deals/{deal_id}
  PATCH /deals/{deal_id}/outcome
  POST /deals/{deal_id}/decision
  GET/POST /watchlists
  DELETE /watchlists/{filter_id}
  GET  /stats/pipeline
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.core.settings import cors_origins, pipeline_mode
from backend.db.client import (
    delete_watchlist as remove_watchlist,
    fetch_deal,
    find_deal_by_url,
    list_deals as fetch_deals,
    list_watchlists as fetch_watchlists,
    pipeline_stats as fetch_pipeline_stats,
    save_deal,
    save_watchlist,
)
from shared.schemas.deal import DealPayload, DealStatus, WatchlistFilter


# ─── App Lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Touch the store so demo deals exist before the first request.
    fetch_deals(limit=1)
    print("Deaven API starting...")
    yield
    print("Deaven API shutting down...")


app = FastAPI(
    title="Deaven API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response Models ──────────────────────────────────────────────────

class IngestURLRequest(BaseModel):
    url: str


class OutcomeUpdateRequest(BaseModel):
    purchase_price: Optional[float] = None
    sale_price: Optional[float] = None
    days_to_sell: Optional[int] = None
    recon_actual: Optional[float] = None
    lemon: bool = False
    human_decision: Optional[str] = None


class DealSummary(BaseModel):
    deal_id: str
    source: str
    url: str
    title: str
    price: float
    year: Optional[int]
    make: Optional[str]
    model: Optional[str]
    deal_score: Optional[float]
    deal_tier: Optional[str]
    narrative: Optional[str]
    status: str
    ingested_at: datetime
    flags: list[str]


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "pipeline_mode": pipeline_mode(),
    }


@app.post("/deals/ingest", response_model=DealSummary)
async def ingest_deal(req: IngestURLRequest):
    from backend.agents.scout import ingest_url

    existing = find_deal_by_url(req.url)
    payload = await ingest_url(req.url)
    if existing is not None:
        payload.deal_id = existing.deal_id
    save_deal(payload)
    return _to_summary(payload)


@app.get("/deals", response_model=list[DealSummary])
async def list_deals(
    tier: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    return [_to_summary(p) for p in fetch_deals(tier=tier, status=status, limit=limit)]


@app.get("/deals/{deal_id}", response_model=DealPayload)
async def get_deal(deal_id: str):
    deal = fetch_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@app.patch("/deals/{deal_id}/outcome")
async def update_outcome(deal_id: str, req: OutcomeUpdateRequest):
    deal = _require_deal(deal_id)
    if req.purchase_price is not None:
        deal.outcome_purchase_price = req.purchase_price
    if req.sale_price is not None:
        deal.outcome_sale_price = req.sale_price
    if req.days_to_sell is not None:
        deal.outcome_days_to_sell = req.days_to_sell
    if req.recon_actual is not None:
        deal.outcome_recon_actual = req.recon_actual
    deal.outcome_lemon = req.lemon
    if req.human_decision is not None:
        deal.human_decision = req.human_decision
    if req.purchase_price is not None and req.sale_price is not None:
        cost = req.purchase_price + (req.recon_actual or 0)
        if req.sale_price:
            deal.outcome_margin_actual = (req.sale_price - cost) / req.sale_price
        if req.sale_price > 0:
            deal.status = DealStatus.SOLD
    save_deal(deal)
    return {"deal_id": deal_id, "updated": True}


@app.post("/deals/{deal_id}/decision")
async def record_decision(deal_id: str, decision: str):
    deal = _require_deal(deal_id)
    deal.human_decision = decision
    if decision == "acquire":
        deal.status = DealStatus.ACTIONED
    elif decision == "pass":
        deal.status = DealStatus.DISCARDED
    elif decision == "watchlist":
        deal.status = DealStatus.SCORED
    save_deal(deal)
    return {"deal_id": deal_id, "decision": decision}


@app.get("/watchlists", response_model=list[WatchlistFilter])
async def list_watchlists():
    return fetch_watchlists()


@app.post("/watchlists", response_model=WatchlistFilter)
async def create_watchlist(f: WatchlistFilter):
    return save_watchlist(f)


@app.delete("/watchlists/{filter_id}")
async def delete_watchlist(filter_id: str):
    if not remove_watchlist(filter_id):
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return {"deleted": filter_id}


@app.get("/stats/pipeline")
async def pipeline_stats():
    return fetch_pipeline_stats()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _require_deal(deal_id: str) -> DealPayload:
    deal = fetch_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


def _to_summary(p: DealPayload) -> DealSummary:
    source = p.source.value if hasattr(p.source, "value") else str(p.source)
    tier = p.deal_tier.value if hasattr(p.deal_tier, "value") else p.deal_tier
    status = p.status.value if hasattr(p.status, "value") else str(p.status)
    return DealSummary(
        deal_id=p.deal_id,
        source=source,
        url=p.url,
        title=p.listing.title,
        price=p.listing.price,
        year=p.listing.year,
        make=p.listing.make,
        model=p.listing.model,
        deal_score=p.deal_score,
        deal_tier=tier,
        narrative=p.narrative,
        status=status,
        ingested_at=p.ingested_at,
        flags=p.flags,
    )
