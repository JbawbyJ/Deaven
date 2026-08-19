"""
backend/api/main.py
FastAPI application — REST API for the Deaven dashboard.
"""

from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.schemas.deal import DealPayload, DealSource, DealStatus, DealTier, WatchlistFilter
from backend.core.orchestrator import DealOrchestrator
from backend.agents.scout import ingest_url
from backend.db.client import save_deal, get_deal as fetch_deal


# ─── App Lifecycle ────────────────────────────────────────────────────────────

orchestrator = DealOrchestrator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Deaven API starting...")
    yield
    print("Deaven API shutting down...")

app = FastAPI(
    title    = "Deaven API",
    version  = "0.1.0",
    lifespan = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:5173"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─── Request/Response Models ──────────────────────────────────────────────────

class IngestURLRequest(BaseModel):
    url: str

class OutcomeUpdateRequest(BaseModel):
    purchase_price:  Optional[float] = None
    sale_price:      Optional[float] = None
    days_to_sell:    Optional[int]   = None
    recon_actual:    Optional[float] = None
    lemon:           bool            = False
    human_decision:  Optional[str]   = None

class DealSummary(BaseModel):
    deal_id:     str
    source:      str
    url:         str
    title:       str
    price:       float
    year:        Optional[int]
    make:        Optional[str]
    model:       Optional[str]
    deal_score:  Optional[float]
    deal_tier:   Optional[str]
    narrative:   Optional[str]
    status:      str
    ingested_at: datetime
    flags:       list[str]


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/deals/ingest", response_model=DealSummary)
async def ingest_deal(req: IngestURLRequest, background_tasks: BackgroundTasks):
    payload = await ingest_url(req.url)
    save_deal(payload)
    background_tasks.add_task(orchestrator.process_deal, payload)
    return _to_summary(payload)


@app.get("/deals", response_model=list[DealSummary])
async def list_deals(
    tier:   Optional[str] = None,
    status: Optional[str] = None,
    limit:  int           = 50,
):
    # TODO: query Supabase with filters
    return []


@app.get("/deals/{deal_id}", response_model=DealPayload)
async def get_deal(deal_id: str):
    deal = fetch_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@app.patch("/deals/{deal_id}/outcome")
async def update_outcome(deal_id: str, req: OutcomeUpdateRequest):
    # TODO: update Supabase record
    return {"deal_id": deal_id, "updated": True}


@app.post("/deals/{deal_id}/decision")
async def record_decision(deal_id: str, decision: str):
    # TODO: update DB + trigger RL reward calculation
    return {"deal_id": deal_id, "decision": decision}


@app.get("/watchlists", response_model=list[WatchlistFilter])
async def list_watchlists():
    # TODO: fetch from Supabase
    return []


@app.post("/watchlists", response_model=WatchlistFilter)
async def create_watchlist(f: WatchlistFilter):
    # TODO: save to Supabase
    return f


@app.delete("/watchlists/{filter_id}")
async def delete_watchlist(filter_id: str):
    # TODO: delete from Supabase
    return {"deleted": filter_id}


@app.get("/stats/pipeline")
async def pipeline_stats():
    # TODO: aggregate from Supabase
    return {
        "total_ingested":  0,
        "fire_deals":      0,
        "strong_deals":    0,
        "watchlist_deals": 0,
        "avg_score":       0,
        "avg_margin":      0,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _to_summary(p: DealPayload) -> DealSummary:
    return DealSummary(
        deal_id     = p.deal_id,
        source      = p.source,
        url         = p.url,
        title       = p.listing.title,
        price       = p.listing.price,
        year        = p.listing.year,
        make        = p.listing.make,
        model       = p.listing.model,
        deal_score  = p.deal_score,
        deal_tier   = p.deal_tier,
        narrative   = p.narrative,
        status      = p.status,
        ingested_at = p.ingested_at,
        flags       = p.flags,
    )