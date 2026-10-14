"""Write JSON Schema files from the listing models.

Run from the repo root:

    python scripts/export_schemas.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.schemas.listing import (
    CanonicalListing,
    ListingLocation,
    ListingPhoto,
    NormalizedListing,
    RawProvenance,
)
from shared.schemas.market import PriceObservation, Seller, Source, VehicleCluster

MODELS = (
    ListingLocation,
    ListingPhoto,
    RawProvenance,
    NormalizedListing,
    CanonicalListing,
    Source,
    Seller,
    PriceObservation,
    VehicleCluster,
)

OUT_DIR = Path(__file__).resolve().parents[1] / "shared" / "schemas" / "json"


def rendered_schemas() -> dict[str, str]:
    """Filename -> canonical JSON text. Key order is sorted so the files stay stable."""
    rendered: dict[str, str] = {}
    for model in MODELS:
        text = json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        rendered[f"{model.__name__}.schema.json"] = text
    return rendered


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    expected = rendered_schemas()
    for name, text in expected.items():
        (OUT_DIR / name).write_text(text, encoding="utf-8")
    stale = [path.name for path in OUT_DIR.glob("*.schema.json") if path.name not in expected]
    for name in stale:
        (OUT_DIR / name).unlink()


if __name__ == "__main__":
    main()
