"""
shared/schemas/deal.py
Core data contracts. Every agent reads and writes DealPayload.
This is the single source of truth across the entire pipeline.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


# ─── Enums ────────────────────────────────────────────────────────────────────

class DealSource(str, Enum):
    BRING_A_TRAILER = "bat"
    CARS_AND_BIDS   = "cab"
    EBAY            = "ebay"
    CLASSIC_COM     = "classic_com"
    TCV             = "tcv"
    FACEBOOK        = "facebook"
    AUTOTRADER      = "autotrader"
    HEMMINGS        = "hemmings"
    CRAIGSLIST      = "craigslist"
    MANUAL          = "manual"

class DealTier(str, Enum):
    FIRE      = "fire"       # 85–100
    STRONG    = "strong"     # 70–84
    WATCHLIST = "watchlist"  # 55–69
    PASS      = "pass"       # 40–54
    DISCARD   = "discard"    # 0–39

class DealStatus(str, Enum):
    INGESTED    = "ingested"
    TRIAGED     = "triaged"
    SCORING     = "scoring"
    SCORED      = "scored"
    ACTIONED    = "actioned"
    ACQUIRED    = "acquired"
    SOLD        = "sold"
    DISCARDED   = "discarded"

class ConditionGrade(str, Enum):
    A = "A"   # Concours / like new
    B = "B"   # Excellent driver
    C = "C"   # Good, minor flaws
    D = "D"   # Fair, needs work
    F = "F"   # Project / parts car


# ─── Raw Listing ──────────────────────────────────────────────────────────────

class ListingData(BaseModel):
    title:        str
    price:        float
    mileage:      Optional[int]    = None
    year:         Optional[int]    = None
    make:         Optional[str]    = None
    model:        Optional[str]    = None
    trim:         Optional[str]    = None
    vin:          Optional[str]    = None
    location:     Optional[str]    = None
    description:  Optional[str]    = None
    seller_type:  Optional[str]    = None   # "private" | "dealer"
    listing_date: Optional[datetime] = None
    end_date:     Optional[datetime] = None  # for auctions
    watch_count:  Optional[int]    = None
    bid_count:    Optional[int]    = None
    color_ext:    Optional[str]    = None
    color_int:    Optional[str]    = None
    transmission: Optional[str]    = None
    drivetrain:   Optional[str]    = None


# ─── Agent Reports ────────────────────────────────────────────────────────────

class VisionReport(BaseModel):
    exterior_grade:   ConditionGrade
    interior_grade:   ConditionGrade
    engine_bay_grade: Optional[ConditionGrade] = None
    undercarriage_grade: Optional[ConditionGrade] = None
    flags:            list[str]  = Field(default_factory=list)
    # e.g. ["possible_repaint_rear_quarter", "rust_rocker_panel", "curb_rash_wheels"]
    condition_score:  float      # 0–100, feeds into scoring engine
    photo_count:      int
    confidence:       float      # 0–1, low if photos are bad/missing
    raw_analysis:     Optional[str] = None  # Claude Vision narrative

    @classmethod
    def degraded(cls) -> "VisionReport":
        """Fallback when vision agent fails — neutral score, flagged for review."""
        return cls(
            exterior_grade=ConditionGrade.C,
            interior_grade=ConditionGrade.C,
            flags=["vision_agent_failed"],
            condition_score=50.0,
            photo_count=0,
            confidence=0.1,
        )


class RiskReport(BaseModel):
    owner_count:       Optional[int]  = None
    accident_count:    Optional[int]  = None
    title_clean:       bool           = True
    title_flags:       list[str]      = Field(default_factory=list)
    # e.g. ["salvage", "flood", "lemon_law", "odometer_rollback"]
    recall_count:      int            = 0
    open_recalls:      list[str]      = Field(default_factory=list)
    service_record_completeness: float = 0.5   # 0–1
    provenance_score:  float          = 50.0   # 0–100
    auto_disqualify:   bool           = False
    disqualify_reason: Optional[str]  = None

    @classmethod
    def degraded(cls) -> "RiskReport":
        """Fallback when VIN check fails."""
        return cls(
            title_flags=["vin_check_failed"],
            provenance_score=40.0,
        )


class ValuationReport(BaseModel):
    comp_avg:                float
    comp_low:                float
    comp_high:               float
    comp_sample_size:        int
    price_vs_comp_pct:       float   # negative = below market (good)
    estimated_retail:        float
    estimated_recon:         float   = 0.0
    estimated_transport:     float   = 0.0
    estimated_gross_margin:  float   # as decimal, e.g. 0.19
    days_to_sell_avg:        int     = 45
    demand_score:            float   # 0–100
    price_score:             float   # 0–100
    margin_score:            float   # 0–100
    search_trend_30d:        Optional[float] = None  # 0–1


# ─── Score Components ─────────────────────────────────────────────────────────

class ScoreComponents(BaseModel):
    price_score:      float   # 0–100
    provenance_score: float   # 0–100
    demand_score:     float   # 0–100
    condition_score:  float   # 0–100
    margin_score:     float   # 0–100

    # Weights
    W_PRICE:      float = 0.30
    W_PROVENANCE: float = 0.25
    W_DEMAND:     float = 0.20
    W_CONDITION:  float = 0.15
    W_MARGIN:     float = 0.10

    def compute(self) -> float:
        return round(
            self.price_score      * self.W_PRICE      +
            self.provenance_score * self.W_PROVENANCE  +
            self.demand_score     * self.W_DEMAND      +
            self.condition_score  * self.W_CONDITION   +
            self.margin_score     * self.W_MARGIN,
            1
        )


# ─── Outreach ─────────────────────────────────────────────────────────────────

class OutreachDraft(BaseModel):
    subject:    str
    body:       str
    channel:    str    # "email" | "platform_message"
    status:     str = "pending_review"   # human reviews before send


# ─── Core Deal Payload ────────────────────────────────────────────────────────

class DealPayload(BaseModel):
    # Identity
    deal_id:     str          = Field(default_factory=lambda: str(uuid.uuid4()))
    source:      DealSource
    url:         str
    ingested_at: datetime     = Field(default_factory=datetime.utcnow)

    # Raw listing
    listing:     ListingData
    images:      list[str]    = Field(default_factory=list)

    # Agent outputs (None until that agent runs)
    vision_report:    Optional[VisionReport]    = None
    risk_report:      Optional[RiskReport]      = None
    valuation_report: Optional[ValuationReport] = None
    outreach_draft:   Optional[OutreachDraft]   = None

    # Scoring
    score_components: Optional[ScoreComponents] = None
    deal_score:       Optional[float]           = None
    deal_tier:        Optional[DealTier]        = None
    narrative:        Optional[str]             = None  # LLM-generated summary

    # Pipeline state
    status:    DealStatus  = DealStatus.INGESTED
    flags:     list[str]   = Field(default_factory=list)
    errors:    list[str]   = Field(default_factory=list)

    # Outcome tracking (filled after deal resolves — feeds ML/RL)
    human_decision:       Optional[str]   = None  # "acquire" | "pass" | "watchlist"
    outcome_purchase_price: Optional[float] = None
    outcome_sale_price:     Optional[float] = None
    outcome_days_to_sell:   Optional[int]   = None
    outcome_recon_actual:   Optional[float] = None
    outcome_margin_actual:  Optional[float] = None
    outcome_lemon:          bool            = False

    class Config:
        use_enum_values = True


# ─── Watchlist Filters ────────────────────────────────────────────────────────

class WatchlistFilter(BaseModel):
    """One saved search / alert rule."""
    filter_id:    str = Field(default_factory=lambda: str(uuid.uuid4()))
    name:         str
    makes:        list[str]  = Field(default_factory=list)
    models:       list[str]  = Field(default_factory=list)
    year_min:     Optional[int]   = None
    year_max:     Optional[int]   = None
    price_min:    Optional[float] = None
    price_max:    Optional[float] = None
    mileage_max:  Optional[int]   = None
    sources:      list[DealSource] = Field(default_factory=list)
    alert_on_tier: list[DealTier]  = Field(default_factory=lambda: [DealTier.FIRE, DealTier.STRONG])
    active:       bool = True
