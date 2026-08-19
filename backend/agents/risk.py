"""
backend/agents/risk.py
Risk Agent — VIN decode, title check, recall lookup, provenance scoring.
Auto-disqualifies on hard flags (salvage, flood, odometer rollback).
"""

from __future__ import annotations
import logging
from typing import Optional

import httpx

from shared.schemas.deal import DealPayload, RiskReport

logger = logging.getLogger(__name__)


# ─── Hard Disqualifiers ───────────────────────────────────────────────────────

HARD_DISQUALIFIERS = {
    "salvage":            "Salvage title — auto-disqualified",
    "flood":              "Flood damage reported — auto-disqualified",
    "fire":               "Fire damage reported — auto-disqualified",
    "odometer_rollback":  "Odometer rollback detected — auto-disqualified",
    "junk":               "Junk title — auto-disqualified",
    "dismantled":         "Dismantled title — auto-disqualified",
}

# Flags that reduce score but don't disqualify
SOFT_FLAGS = {
    "lemon_law":          -20,
    "accident_minor":     -10,
    "accident_major":     -25,
    "rental":             -10,
    "fleet":              -8,
    "frame_damage":       -30,
    "airbag_deployed":    -15,
    "theft_recovered":    -20,
}


# ─── NHTSA Recall Client ──────────────────────────────────────────────────────

class NHTSAClient:
    """Free NHTSA API — no key required."""

    BASE = "https://api.nhtsa.gov/recalls/recallsByVehicle"

    async def get_recalls(self, make: str, model: str, year: int) -> list[dict]:
        params = {"make": make, "model": model, "modelYear": year}
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(self.BASE, params=params)
                resp.raise_for_status()
                return resp.json().get("results", [])
            except Exception as e:
                logger.warning(f"NHTSA lookup failed: {e}")
                return []


# ─── VIN Decoder ─────────────────────────────────────────────────────────────

class VINDecoder:
    """
    NHTSA free VIN decode API.
    For Carfax/AutoCheck integration: swap this client.
    """

    BASE = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevin"

    async def decode(self, vin: str) -> dict:
        url = f"{self.BASE}/{vin}?format=json"
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                results = resp.json().get("Results", [])
                return {r["Variable"]: r["Value"] for r in results if r.get("Value")}
            except Exception as e:
                logger.warning(f"VIN decode failed ({vin}): {e}")
                return {}


# ─── Carfax / AutoCheck Stub ──────────────────────────────────────────────────

class CarfaxClient:
    """
    Production: Carfax Partner API (requires agreement with Carfax).
    Stub returns empty report. Replace with real API calls.
    """

    async def get_report(self, vin: str, api_key: str) -> dict:
        """
        Returns dict with keys:
          owner_count, accident_count, title_flags, service_records,
          odometer_readings, lemon_law, rental, fleet
        """
        # TODO: implement with Carfax Partner API
        # https://www.carfax.com/partner/
        logger.warning("Carfax API not configured — returning empty report")
        return {}


# ─── Risk Agent ───────────────────────────────────────────────────────────────

class RiskAgent:
    """
    Runs VIN history, title check, and recall lookup.
    Returns a RiskReport with provenance_score and auto_disqualify flag.
    """

    def __init__(
        self,
        carfax_api_key: Optional[str] = None,
        autocheck_api_key: Optional[str] = None,
    ):
        self.carfax_key   = carfax_api_key
        self.nhtsa        = NHTSAClient()
        self.vin_decoder  = VINDecoder()
        self.carfax       = CarfaxClient()

    async def run(self, payload: DealPayload) -> RiskReport:
        """Main entry. Returns RiskReport."""

        vin   = payload.listing.vin
        make  = payload.listing.make  or ""
        model = payload.listing.model or ""
        year  = payload.listing.year  or 0

        # 1. VIN decode (free, always run)
        vin_data     = await self.vin_decoder.decode(vin) if vin else {}

        # 2. Carfax history (paid, if configured)
        carfax_data  = {}
        if vin and self.carfax_key:
            carfax_data = await self.carfax.get_report(vin, self.carfax_key)

        # 3. NHTSA recalls (free, always run if make/model/year available)
        recalls = []
        if make and model and year:
            recalls = await self.nhtsa.get_recalls(make, model, year)

        # 4. Build report
        report = self._build_report(vin_data, carfax_data, recalls)

        logger.info(
            f"[{payload.deal_id}] Risk: score={report.provenance_score} "
            f"disqualify={report.auto_disqualify} flags={report.title_flags}"
        )
        return report

    def _build_report(
        self,
        vin_data:    dict,
        carfax_data: dict,
        recalls:     list[dict],
    ) -> RiskReport:

        title_flags     = []
        score_penalty   = 0
        auto_disqualify = False
        disqualify_reason = None

        # --- Parse Carfax flags ---
        cf_title_flags = carfax_data.get("title_flags", [])
        for flag in cf_title_flags:
            flag_lower = flag.lower()
            if flag_lower in HARD_DISQUALIFIERS:
                auto_disqualify   = True
                disqualify_reason = HARD_DISQUALIFIERS[flag_lower]
                title_flags.append(flag_lower)
            elif flag_lower in SOFT_FLAGS:
                score_penalty += abs(SOFT_FLAGS[flag_lower])
                title_flags.append(flag_lower)

        # --- Owner & accident counts ---
        owner_count    = carfax_data.get("owner_count")
        accident_count = carfax_data.get("accident_count", 0)
        if accident_count and accident_count > 0:
            if accident_count >= 2:
                score_penalty += 25
                title_flags.append("accident_major")
            else:
                score_penalty += 10
                title_flags.append("accident_minor")

        # --- Service record completeness ---
        service_completeness = carfax_data.get("service_completeness", 0.5)

        # --- Open recalls ---
        open_recalls     = [r.get("Component", r.get("Summary", "")) for r in recalls]
        recall_count     = len(recalls)

        # --- Build provenance score ---
        base_score = 100

        # Owner count penalty
        if owner_count:
            if owner_count == 1:
                pass              # no penalty
            elif owner_count == 2:
                base_score -= 5
            elif owner_count <= 4:
                base_score -= 15
            else:
                base_score -= 25

        # Service records
        base_score -= int((1 - service_completeness) * 20)

        # Recall penalty (open only)
        base_score -= min(recall_count * 5, 20)

        # Apply accumulated penalties
        base_score -= score_penalty

        provenance_score = max(0.0, float(base_score))

        return RiskReport(
            owner_count              = owner_count,
            accident_count           = accident_count,
            title_clean              = len(title_flags) == 0,
            title_flags              = title_flags,
            recall_count             = recall_count,
            open_recalls             = open_recalls,
            service_record_completeness = service_completeness,
            provenance_score         = provenance_score,
            auto_disqualify          = auto_disqualify,
            disqualify_reason        = disqualify_reason,
        )
