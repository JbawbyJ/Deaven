"""Offline VIN normalization, check digit, and ISO 3779 decode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from shared.vin.tables import (
    COUNTRIES,
    MANUFACTURERS,
    REGIONS,
    TRANSLITERATION,
    WEIGHTS,
    YEAR_CODES,
)

_ALLOWED = frozenset(TRANSLITERATION)
_STRIP = str.maketrans("", "", " -")
_NORTH_AMERICA = frozenset("12345")


def normalize_vin(raw: str | None) -> str | None:
    """Return a canonical 17-character VIN, or None when the input cannot be one.

    Trims, uppercases, and removes spaces and dashes. Rejects any value that is
    not 17 characters of the VIN alphabet. I, O, and Q are not in that alphabet.
    """
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().upper().translate(_STRIP)
    if len(cleaned) != 17 or any(char not in _ALLOWED for char in cleaned):
        return None
    return cleaned


def expected_check_digit(vin: str) -> str:
    """ISO 3779 / 49 CFR 565 check character for an already-normalized VIN."""
    total = sum(TRANSLITERATION[char] * weight for char, weight in zip(vin, WEIGHTS))
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def validate_check_digit(raw: str | None) -> bool | None:
    """Whether position 9 matches the check digit.

    None means the input is not a normalizable VIN. False is information:
    many VINs issued outside North America do not use this check digit, and
    callers must not drop a listing only because this returns False.
    """
    vin = normalize_vin(raw)
    if vin is None:
        return None
    return vin[8] == expected_check_digit(vin)


def vin_key(raw: str | None) -> str | None:
    """Stable dedupe key for one vehicle across sources.

    The key is the canonical VIN, so casing, spaces, and dashes collapse.
    A different 17-character VIN, including one whose check digit was
    transcribed differently, stays a different vehicle.
    """
    return normalize_vin(raw)


@dataclass(frozen=True, slots=True)
class VinDecode:
    """Offline decode. `model_year` may be ambiguous; see `model_year_candidates`."""

    vin: str
    wmi: str
    vds: str
    vis: str
    region: str | None
    country: str | None
    manufacturer: str | None
    model_year: int | None
    model_year_candidates: tuple[int, ...]
    model_year_source: str
    plant_code: str
    serial: str
    check_digit: str
    check_digit_expected: str
    check_digit_valid: bool
    check_digit_applicable: bool


def decode_vin(raw: str | None, *, as_of: date | None = None) -> VinDecode | None:
    """Decode a VIN without the network.

    North American vehicles (WMI region 1–5) use position 7 to choose the
    30-year model-year cycle, per the note to 49 CFR 565: a numeric position 7
    selects 2010–2039 and a letter selects 1980–2009. Some pre-2010 vehicles
    already used a digit in position 7, so that hint can point at the later
    cycle (the familiar Honda `1HGCM82633A004352` resolves to 2033, with 2003
    retained in `model_year_candidates`).

    Other regions do not use position 7 that way. Both cycle years are
    returned, and `model_year` is the later candidate that is not more than
    one year after `as_of` (model years are released the previous calendar year).
    """
    vin = normalize_vin(raw)
    if vin is None:
        return None
    resolved_as_of = as_of or date.today()
    model_year, candidates, source = _model_year(vin, resolved_as_of)
    expected = expected_check_digit(vin)
    north_american = vin[0] in _NORTH_AMERICA
    return VinDecode(
        vin=vin,
        wmi=vin[:3],
        vds=vin[3:9],
        vis=vin[9:],
        region=REGIONS.get(vin[0]),
        country=COUNTRIES.get(vin[:2]),
        manufacturer=MANUFACTURERS.get(vin[:3]),
        model_year=model_year,
        model_year_candidates=candidates,
        model_year_source=source,
        plant_code=vin[10],
        serial=vin[11:],
        check_digit=vin[8],
        check_digit_expected=expected,
        check_digit_valid=vin[8] == expected,
        check_digit_applicable=north_american,
    )


def _model_year(vin: str, as_of: date) -> tuple[int | None, tuple[int, ...], str]:
    pair = YEAR_CODES.get(vin[9])
    if pair is None:
        return None, (), "invalid_year_code"
    early, late = pair
    candidates = (early, late)
    if vin[0] in _NORTH_AMERICA:
        chosen = late if vin[6].isdigit() else early
        return chosen, candidates, "north_america_position_7"
    horizon = as_of.year + 1
    chosen = late if late <= horizon else early
    return chosen, candidates, "latest_not_after_next_model_year"
