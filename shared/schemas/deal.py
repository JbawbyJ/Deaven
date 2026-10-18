"""
shared/schemas/deal.py
Core data contracts. Every agent reads and writes DealPayload.
This is the single source of truth across the entire pipeline.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
import re
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import uuid

from shared.vin import VinError, validate_vin
from shared.zip_centroids import centroid_for_zip


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

_TRIM_SEPARATOR = re.compile(r"[^\w]+", re.UNICODE)


def normalize_trim(value: Optional[str]) -> Optional[str]:
    """Lowercase a trim and collapse whitespace and punctuation to one space.

    There is no curated trim vocabulary. "SZ-R" becomes "sz r".
    """
    if value is None:
        return None
    parts = [part for part in _TRIM_SEPARATOR.split(value.lower().replace("_", " ")) if part]
    collapsed = " ".join(parts)
    return collapsed or None


class ListingData(BaseModel):
    """Source listing facts shared with pricing and the UI.

    `price` and `asking_price` are the same asking amount in major currency
    units (dollars when `currency` is USD), matching the existing `price`
    field. `listing_id` is `{source}:{source_id}` when those parts are known.
    A present `vin` is stored uppercase and must pass the ISO 3779 check digit.
    `trim_normalized` is always derived from `trim`. `canonical_id` stays
    empty until dedupe assigns one; every source row in a cluster keeps its
    own fields and shares that id.
    `lat` and `lng` are optional. Source coordinates are kept. If both are
    missing and `zip` is in the offline centroid table, those centroids are
    filled in. Unknown zips leave both null.
    """

    title:        str
    price:        float
    asking_price: Optional[float] = None
    sold_price:   Optional[float] = None
    sold_at:      Optional[datetime] = None
    currency:     str = "USD"

    mileage:      Optional[int]    = None
    year:         Optional[int]    = None
    make:         Optional[str]    = None
    model:        Optional[str]    = None
    trim:         Optional[str]    = None
    trim_normalized: Optional[str] = None
    vin:          Optional[str]    = None

    location:     Optional[str]    = None   # display string, e.g. "Austin, TX"
    region:       Optional[str]    = None   # state/province code
    zip:          Optional[str]    = None
    lat:          Optional[float]  = Field(default=None, ge=-90, le=90)
    lng:          Optional[float]  = Field(default=None, ge=-180, le=180)

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

    source:       Optional[str]    = None
    source_id:    Optional[str]    = None
    listing_id:   Optional[str]    = None   # "{source}:{source_id}"
    canonical_id: Optional[str]    = None

    @model_validator(mode="before")
    @classmethod
    def _asking_price_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "asking_price" not in data:
            return data
        incoming = dict(data)
        asking = incoming.get("asking_price")
        if asking is None:
            return incoming
        if incoming.get("price") is None:
            incoming["price"] = asking
        elif float(asking) != float(incoming["price"]):
            raise ValueError("asking_price must match price")
        return incoming

    @field_validator("vin", mode="before")
    @classmethod
    def _vin(cls, value: Any) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        try:
            return validate_vin(str(value))
        except VinError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("trim", "location", "zip", "canonical_id", "source_id", "listing_id", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("region", mode="before")
    @classmethod
    def _region(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if len(text) == 2 and text.isalpha():
            return text.upper()
        return text

    @field_validator("source", mode="before")
    @classmethod
    def _source(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, Enum):
            value = value.value
        text = str(value).strip()
        if not text:
            return None
        if ":" in text:
            raise ValueError("source must not contain ':'")
        return text

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, value: Any) -> str:
        if value is None or not str(value).strip():
            return "USD"
        code = str(value).strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return code

    @model_validator(mode="after")
    def _derived_fields(self) -> "ListingData":
        self.trim_normalized = normalize_trim(self.trim)
        if self.asking_price is None:
            self.asking_price = self.price
        self.listing_id = _compose_listing_id(self.source, self.source_id, self.listing_id)
        if self.listing_id:
            source, source_id = self.listing_id.split(":", 1)
            self.source = source
            self.source_id = source_id
        _fill_coordinates(self)
        return self


def _compose_listing_id(
    source: Optional[str],
    source_id: Optional[str],
    listing_id: Optional[str],
) -> Optional[str]:
    if source and source_id:
        composed = f"{source}:{source_id}"
        if listing_id and listing_id != composed:
            raise ValueError("listing_id must be '{source}:{source_id}'")
        return composed
    if not listing_id:
        return None
    if ":" not in listing_id:
        raise ValueError("listing_id must be '{source}:{source_id}'")
    parsed_source, parsed_id = listing_id.split(":", 1)
    if not parsed_source or not parsed_id:
        raise ValueError("listing_id must be '{source}:{source_id}'")
    if source and source != parsed_source:
        raise ValueError("listing_id must be '{source}:{source_id}'")
    if source_id and source_id != parsed_id:
        raise ValueError("listing_id must be '{source}:{source_id}'")
    if ":" in parsed_source:
        raise ValueError("source must not contain ':'")
    return listing_id


def _fill_coordinates(listing: ListingData) -> None:
    has_lat = listing.lat is not None
    has_lng = listing.lng is not None
    if has_lat != has_lng:
        raise ValueError("lat and lng must be set together")
    if has_lat or not listing.zip:
        return
    found = centroid_for_zip(listing.zip)
    if found is None:
        return
    listing.lat, listing.lng = found


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
