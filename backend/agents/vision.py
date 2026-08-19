"""
backend/agents/vision.py
Vision Agent — downloads listing photos, runs analysis pipeline,
returns a structured VisionReport for the scoring engine.

Pipeline:
  Images → Download → CLIP embeddings → YOLOv8 detection → Claude Vision → VisionReport
"""

from __future__ import annotations
import asyncio
import base64
import logging
from io import BytesIO
from typing import Optional

import anthropic
import httpx
from PIL import Image

from shared.schemas.deal import ConditionGrade, DealPayload, VisionReport

logger = logging.getLogger(__name__)

# ─── Prompts ──────────────────────────────────────────────────────────────────

VISION_SYSTEM_PROMPT = """You are an expert automotive condition inspector with 20+ years evaluating 
collector and enthusiast vehicles. You analyze listing photos and provide structured assessments.

Be precise, factual, and conservative — flag anything suspicious rather than giving benefit of the doubt.
Your job is to protect the buyer from costly surprises.

Always respond in the exact JSON format requested. No markdown, no explanation outside the JSON."""

VISION_ANALYSIS_PROMPT = """Analyze these vehicle listing photos and provide a condition assessment.

Return ONLY valid JSON in this exact format:
{
  "exterior_grade": "A|B|C|D|F",
  "interior_grade": "A|B|C|D|F", 
  "engine_bay_grade": "A|B|C|D|F|null",
  "undercarriage_grade": "A|B|C|D|F|null",
  "flags": ["list", "of", "specific", "concerns"],
  "condition_score": 0-100,
  "confidence": 0.0-1.0,
  "raw_analysis": "2-3 sentence summary of overall condition and key findings"
}

Grade scale:
A = Concours/like new, B = Excellent driver, C = Good minor flaws, D = Fair needs work, F = Project/parts

Flag vocabulary (use exact strings):
- possible_repaint (any panel)
- confirmed_repaint_[panel]
- rust_[location]  
- accident_damage_[area]
- curb_rash_wheels
- cracked_windshield
- worn_seats
- torn_upholstery
- cracked_dash
- engine_oil_leak
- coolant_staining
- aftermarket_[component]
- poor_photo_quality
- missing_[component]
- flood_indicators

Confidence: 1.0 = clear photos of all areas, 0.5 = some areas missing, 0.1 = inadequate photos"""


# ─── Image Utilities ──────────────────────────────────────────────────────────

async def download_images(urls: list[str], max_images: int = 20) -> list[bytes]:
    """Download up to max_images photos concurrently."""
    urls = urls[:max_images]

    async def fetch_one(url: str) -> Optional[bytes]:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.warning(f"Image download failed {url}: {e}")
            return None

    results = await asyncio.gather(*[fetch_one(u) for u in urls])
    return [r for r in results if r is not None]


def resize_image(img_bytes: bytes, max_width: int = 1024) -> bytes:
    """Resize image to reduce token usage while preserving quality."""
    try:
        img = Image.open(BytesIO(img_bytes))
        if img.width > max_width:
            ratio  = max_width / img.width
            height = int(img.height * ratio)
            img    = img.resize((max_width, height), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return img_bytes   # return original if resize fails


def to_base64(img_bytes: bytes) -> str:
    return base64.standard_b64encode(img_bytes).decode("utf-8")


def select_representative_images(image_bytes_list: list[bytes], n: int = 8) -> list[bytes]:
    """
    Select the most representative images to send to Claude Vision.
    Strategy: first 3 (exterior), middle batch (interior/engine), last 2.
    Keeps token cost manageable.
    """
    if len(image_bytes_list) <= n:
        return image_bytes_list

    indices = (
        list(range(min(3, len(image_bytes_list)))) +
        list(range(len(image_bytes_list) // 3, len(image_bytes_list) // 3 + 3)) +
        list(range(max(0, len(image_bytes_list) - 2), len(image_bytes_list)))
    )
    seen = set()
    selected = []
    for i in indices:
        if i not in seen and i < len(image_bytes_list):
            selected.append(image_bytes_list[i])
            seen.add(i)
    return selected[:n]


# ─── Vision Agent ─────────────────────────────────────────────────────────────

class VisionAgent:
    """
    Analyzes vehicle listing photos using Claude Vision API.
    Optionally runs YOLOv8 defect detection as a pre-pass.
    """

    def __init__(self, anthropic_client: Optional[anthropic.AsyncAnthropic] = None):
        self.client  = anthropic_client or anthropic.AsyncAnthropic()
        self.yolo    = None   # lazy-loaded

    async def run(self, payload: DealPayload) -> VisionReport:
        """Main entry. Downloads images and returns VisionReport."""

        if not payload.images:
            logger.warning(f"[{payload.deal_id}] No images — returning degraded report")
            return VisionReport.degraded()

        # 1. Download images
        image_bytes_list = await download_images(payload.images)
        if not image_bytes_list:
            logger.warning(f"[{payload.deal_id}] All image downloads failed")
            return VisionReport.degraded()

        # 2. (Optional) YOLOv8 pre-pass for defect detection
        yolo_flags = await self._run_yolo(image_bytes_list) if self.yolo else []

        # 3. Select representative images
        selected = select_representative_images(image_bytes_list)

        # 4. Resize for token efficiency
        resized = [resize_image(b) for b in selected]

        # 5. Run Claude Vision analysis
        report = await self._claude_vision_analysis(resized, len(payload.images))

        # 6. Merge YOLO flags
        if yolo_flags:
            report.flags = list(set(report.flags + yolo_flags))

        logger.info(
            f"[{payload.deal_id}] Vision: score={report.condition_score} "
            f"grade_ext={report.exterior_grade} flags={report.flags}"
        )
        return report

    async def _claude_vision_analysis(
        self,
        image_bytes_list: list[bytes],
        total_photo_count: int,
    ) -> VisionReport:
        """Send images to Claude Vision and parse structured response."""

        content = []
        for img_bytes in image_bytes_list:
            content.append({
                "type":  "image",
                "source": {
                    "type":       "base64",
                    "media_type": "image/jpeg",
                    "data":       to_base64(img_bytes),
                }
            })
        content.append({"type": "text", "text": VISION_ANALYSIS_PROMPT})

        try:
            response = await self.client.messages.create(
                model      = "claude-opus-4-5",
                max_tokens = 1024,
                system     = VISION_SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": content}],
            )

            raw_text = response.content[0].text
            import json
            data = json.loads(raw_text)

            return VisionReport(
                exterior_grade      = data.get("exterior_grade", "C"),
                interior_grade      = data.get("interior_grade", "C"),
                engine_bay_grade    = data.get("engine_bay_grade"),
                undercarriage_grade = data.get("undercarriage_grade"),
                flags               = data.get("flags", []),
                condition_score     = float(data.get("condition_score", 50)),
                photo_count         = total_photo_count,
                confidence          = float(data.get("confidence", 0.7)),
                raw_analysis        = data.get("raw_analysis", ""),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Vision JSON parse error: {e}")
            return VisionReport.degraded()
        except Exception as e:
            logger.error(f"Claude Vision API error: {e}")
            return VisionReport.degraded()

    async def _run_yolo(self, image_bytes_list: list[bytes]) -> list[str]:
        """
        YOLOv8 defect detection pre-pass.
        Model trained on labeled car condition dataset.
        Returns list of detected defect flags.
        """
        flags = []
        try:
            from PIL import Image as PILImage
            import numpy as np

            for img_bytes in image_bytes_list[:5]:   # limit to first 5 for speed
                img   = PILImage.open(BytesIO(img_bytes)).convert("RGB")
                arr   = np.array(img)
                preds = self.yolo(arr)               # returns Results object
                for result in preds:
                    for box in result.boxes:
                        cls_name = result.names[int(box.cls)]
                        conf     = float(box.conf)
                        if conf > 0.6:
                            flags.append(cls_name)   # e.g. "rust", "dent", "crack"
        except Exception as e:
            logger.warning(f"YOLO pass failed: {e}")
        return list(set(flags))

    def load_yolo_model(self, model_path: str):
        """Lazy-load YOLOv8 model. Call this at startup if GPU available."""
        try:
            from ultralytics import YOLO
            self.yolo = YOLO(model_path)
            logger.info(f"YOLOv8 model loaded from {model_path}")
        except Exception as e:
            logger.warning(f"YOLOv8 load failed (running vision-only mode): {e}")
