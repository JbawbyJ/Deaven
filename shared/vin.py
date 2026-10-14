"""ISO 3779 VIN check-digit validation and offline decode.

The risk agent decodes VINs through NHTSA. `normalize_vin`, `check_digit`,
`validate_vin`, and `is_valid_vin` are the offline check used before a VIN
may identify a listing; they do not call the network. `decode_vpic` is a
separate public NHTSA call and stays off unless explicitly enabled.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.request
from dataclasses import dataclass
from datetime import date

_TRANSLIT: dict[str, int] = {
    **{str(digit): digit for digit in range(10)},
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5,
    "F": 6,
    "G": 7,
    "H": 8,
    "J": 1,
    "K": 2,
    "L": 3,
    "M": 4,
    "N": 5,
    "P": 7,
    "R": 9,
    "S": 2,
    "T": 3,
    "U": 4,
    "V": 5,
    "W": 6,
    "X": 7,
    "Y": 8,
    "Z": 9,
}

# Position 9 (index 8) is the check digit and has weight 0.
_WEIGHTS: tuple[int, ...] = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)

_SEPARATORS = re.compile(r"[\s-]+")


class VinError(ValueError):
    """A VIN failed normalization or the check-digit test."""


def normalize_vin(value: str) -> str:
    """Uppercase a VIN and drop spaces or hyphens."""
    return _SEPARATORS.sub("", value).upper()


def check_digit(vin: str) -> str:
    """Return the expected check character for a normalized 17-character VIN."""
    normalized = normalize_vin(vin)
    if len(normalized) != 17 or any(char not in _TRANSLIT for char in normalized):
        raise VinError("VIN must be 17 transliterable characters")
    total = sum(_TRANSLIT[char] * weight for char, weight in zip(normalized, _WEIGHTS))
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def validate_vin(value: str) -> str:
    """Return a normalized VIN, or raise VinError."""
    vin = normalize_vin(value)
    if len(vin) != 17:
        raise VinError("VIN must be 17 characters")
    if any(char not in _TRANSLIT for char in vin):
        raise VinError("VIN contains an illegal character")
    expected = check_digit(vin)
    if vin[8] != expected:
        raise VinError("VIN check digit is invalid")
    return vin


def is_valid_vin(value: str | None) -> bool:
    if not value:
        return False
    try:
        validate_vin(value)
    except VinError:
        return False
    return True


def vin_key(raw: str) -> str | None:
    """Canonical VIN for dedupe, or None when `validate_vin` would reject it."""
    if not is_valid_vin(raw):
        return None
    return validate_vin(raw)


# Position 10. The same code repeats every 30 years: (1980-2009, 2010-2039).
# U, Z, and 0 are not year codes. I, O, and Q cannot appear in a VIN.
_YEAR_CODES: dict[str, tuple[int, int]] = {
    "A": (1980, 2010),
    "B": (1981, 2011),
    "C": (1982, 2012),
    "D": (1983, 2013),
    "E": (1984, 2014),
    "F": (1985, 2015),
    "G": (1986, 2016),
    "H": (1987, 2017),
    "J": (1988, 2018),
    "K": (1989, 2019),
    "L": (1990, 2020),
    "M": (1991, 2021),
    "N": (1992, 2022),
    "P": (1993, 2023),
    "R": (1994, 2024),
    "S": (1995, 2025),
    "T": (1996, 2026),
    "V": (1997, 2027),
    "W": (1998, 2028),
    "X": (1999, 2029),
    "Y": (2000, 2030),
    "1": (2001, 2031),
    "2": (2002, 2032),
    "3": (2003, 2033),
    "4": (2004, 2034),
    "5": (2005, 2035),
    "6": (2006, 2036),
    "7": (2007, 2037),
    "8": (2008, 2038),
    "9": (2009, 2039),
}

_NORTH_AMERICA = frozenset("12345")

_REGIONS: dict[str, str] = {
    char: name
    for chars, name in (
        ("ABCDEFGH", "Africa"),
        ("JKLMNPR", "Asia"),
        ("STUVWXYZ", "Europe"),
        ("12345", "North America"),
        ("67", "Oceania"),
        ("89", "South America"),
    )
    for char in chars
}


def _countries() -> dict[str, str]:
    """ISO 3780-style country codes from VIN positions 1-2.

    Unlisted pairs stay unknown rather than being guessed.
    """
    table: dict[str, str] = {}

    def assign(first: str, seconds: str, country: str) -> None:
        for char in seconds:
            table[first + char] = country

    vin_chars = "0123456789ABCDEFGHJKLMNPRSTUVWXYZ"
    for first, country in (
        ("1", "United States"),
        ("4", "United States"),
        ("5", "United States"),
        ("2", "Canada"),
        ("J", "Japan"),
        ("L", "China"),
        ("W", "Germany"),
    ):
        assign(first, vin_chars, country)

    assign("3", "ABCDEFGHJKLMNPRSTUVW", "Mexico")  # 3A–3W
    assign("6", "ABCDEFGHJKLMNPRSTUVW", "Australia")  # 6A–6W
    assign("A", "ABCDEFGH", "South Africa")  # AA–AH
    assign("S", "ABCDEFGHJKLM", "United Kingdom")  # SA–SM
    assign("Z", "ABCDEFGHJKLMNPR", "Italy")  # ZA–ZR
    assign("K", "LMNPR", "South Korea")  # KL–KR
    assign("Y", "STUVW", "Sweden")  # YS–YW
    assign("V", "FGHJKLMNPR", "France")  # VF–VR
    assign("9", "ABCDE", "Brazil")  # 9A–9E
    assign("9", "3456789", "Brazil")  # 93–99
    assign("M", "ABCDE", "India")  # MA–ME
    assign("T", "JKLMNP", "Czech Republic")  # TJ–TP
    assign("T", "RSTV", "Hungary")  # TR–TV
    return table


_COUNTRIES = _countries()

# Three-character WMI → make. Common passenger-vehicle codes only.
_MANUFACTURERS: dict[str, str] = {
    "1HG": "Honda",
    "2HG": "Honda",
    "2HK": "Honda",
    "5FN": "Honda",
    "5J6": "Honda",
    "JHM": "Honda",
    "JHL": "Honda",
    "SHH": "Honda",
    "19U": "Acura",
    "19V": "Acura",
    "JH4": "Acura",
    "5J8": "Acura",
    "1NX": "Toyota",
    "2T1": "Toyota",
    "4T1": "Toyota",
    "4T3": "Toyota",
    "4T4": "Toyota",
    "5TD": "Toyota",
    "5TF": "Toyota",
    "JT2": "Toyota",
    "JT3": "Toyota",
    "JTD": "Toyota",
    "JTE": "Toyota",
    "JTM": "Toyota",
    "2T2": "Lexus",
    "JTH": "Lexus",
    "JTJ": "Lexus",
    "1N4": "Nissan",
    "1N6": "Nissan",
    "3N1": "Nissan",
    "5N1": "Nissan",
    "JN1": "Nissan",
    "JN8": "Nissan",
    "JNK": "Infiniti",
    "5N3": "Infiniti",
    "1YV": "Mazda",
    "3MZ": "Mazda",
    "JM1": "Mazda",
    "JM3": "Mazda",
    "4S3": "Subaru",
    "4S4": "Subaru",
    "JF1": "Subaru",
    "JF2": "Subaru",
    "4A3": "Mitsubishi",
    "4A4": "Mitsubishi",
    "JA3": "Mitsubishi",
    "JA4": "Mitsubishi",
    "1FA": "Ford",
    "1FB": "Ford",
    "1FC": "Ford",
    "1FD": "Ford",
    "1FM": "Ford",
    "1FT": "Ford",
    "1ZV": "Ford",
    "2FA": "Ford",
    "3FA": "Ford",
    "3FE": "Ford",
    "6FP": "Ford",
    "1LN": "Lincoln",
    "1G1": "Chevrolet",
    "1GC": "Chevrolet",
    "2G1": "Chevrolet",
    "3G1": "Chevrolet",
    "1G4": "Buick",
    "1GK": "GMC",
    "1GT": "GMC",
    "1G6": "Cadillac",
    "1GY": "Cadillac",
    "1B3": "Dodge",
    "1B7": "Dodge",
    "1D7": "Dodge",
    "1D8": "Dodge",
    "1C3": "Chrysler",
    "2C3": "Chrysler",
    "1C4": "Jeep",
    "1J4": "Jeep",
    "1J8": "Jeep",
    "1C6": "Ram",
    "3C6": "Ram",
    "5YJ": "Tesla",
    "7SA": "Tesla",
    "LRW": "Tesla",
    "WBA": "BMW",
    "WBS": "BMW",
    "WBX": "BMW",
    "WBY": "BMW",
    "4US": "BMW",
    "5UX": "BMW",
    "5YM": "BMW",
    "WMW": "Mini",
    "WDB": "Mercedes-Benz",
    "WDC": "Mercedes-Benz",
    "WDD": "Mercedes-Benz",
    "WDF": "Mercedes-Benz",
    "4JG": "Mercedes-Benz",
    "WA1": "Audi",
    "WAU": "Audi",
    "WUA": "Audi",
    "TRU": "Audi",
    "1VW": "Volkswagen",
    "3VW": "Volkswagen",
    "9BW": "Volkswagen",
    "WV1": "Volkswagen",
    "WV2": "Volkswagen",
    "WVG": "Volkswagen",
    "WVW": "Volkswagen",
    "WP0": "Porsche",
    "WP1": "Porsche",
    "ZFF": "Ferrari",
    "ZHW": "Lamborghini",
    "ZAM": "Maserati",
    "ZAR": "Alfa Romeo",
    "ZFA": "Fiat",
    "SAJ": "Jaguar",
    "SAL": "Land Rover",
    "YV1": "Volvo",
    "YV4": "Volvo",
    "KMH": "Hyundai",
    "KM8": "Hyundai",
    "5NP": "Hyundai",
    "KNA": "Kia",
    "KND": "Kia",
    "5XX": "Kia",
    "5XY": "Kia",
    "VF1": "Renault",
    "VF3": "Peugeot",
    "VF7": "Citroen",
    "TMB": "Skoda",
    "SCC": "Lotus",
    "SCA": "Rolls-Royce",
    "SCF": "Aston Martin",
}


def _structural_vin(value: str) -> str | None:
    """17 transliterable characters, or None. Does not test the check digit."""
    if not isinstance(value, str):
        return None
    vin = normalize_vin(value)
    if len(vin) != 17 or any(char not in _TRANSLIT for char in vin):
        return None
    return vin


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


def decode_vin(value: str, *, as_of: date | None = None) -> VinDecode | None:
    """Decode a VIN without the network.

    Returns None when the value is not 17 transliterable characters. A wrong
    check digit does not reject the decode: `validate_vin` still raises for
    that, and `vin_key` returns None. North American vehicles (WMI region 1–5)
    use position 7 to choose the 30-year model-year cycle, per the note to
    49 CFR 565. A numeric position 7 selects 2010–2039 and a letter selects
    1980–2009. Some pre-2010 vehicles already used a digit in position 7, so
    that hint can point at the later cycle (`1HGCM82633A004352` resolves to
    2033, with 2003 retained in `model_year_candidates`).

    Other regions do not use position 7 that way. Both cycle years are
    returned, and `model_year` is the later candidate that is not more than
    one year after `as_of`.
    """
    vin = _structural_vin(value)
    if vin is None:
        return None
    resolved_as_of = as_of or date.today()
    model_year, candidates, source = _model_year(vin, resolved_as_of)
    expected = check_digit(vin)
    north_american = vin[0] in _NORTH_AMERICA
    return VinDecode(
        vin=vin,
        wmi=vin[:3],
        vds=vin[3:9],
        vis=vin[9:],
        region=_REGIONS.get(vin[0]),
        country=_COUNTRIES.get(vin[:2]),
        manufacturer=_MANUFACTURERS.get(vin[:3]),
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
    pair = _YEAR_CODES.get(vin[9])
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


_logger = logging.getLogger(__name__)

_VPIC_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
_VPIC_CACHE: dict[str, dict] = {}
_VPIC_LOCK = threading.Lock()


def vpic_enabled() -> bool:
    """True when VIN_VPIC_ENABLED is 1/true/yes/on. Default is off. No API key."""
    return os.getenv("VIN_VPIC_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def clear_vpic_cache() -> None:
    with _VPIC_LOCK:
        _VPIC_CACHE.clear()


def decode_vpic(
    raw: str,
    *,
    enabled: bool | None = None,
    timeout: float = 5.0,
    fetch=None,
) -> dict | None:
    """Decode via NHTSA vPIC, or return None.

    `enabled=None` follows VIN_VPIC_ENABLED. Pass True to force a lookup and
    False to skip it. Timeouts, HTTP errors, and malformed payloads return None
    and are not cached. Successful payloads are cached in memory by canonical
    structural VIN. The request carries no credentials. A wrong check digit
    does not block the call; a VIN that is not 17 transliterable characters does.
    """
    if enabled is None:
        enabled = vpic_enabled()
    if not enabled:
        return None
    vin = _structural_vin(raw)
    if vin is None:
        return None

    with _VPIC_LOCK:
        cached = _VPIC_CACHE.get(vin)
    if cached is not None:
        return dict(cached)

    fetcher = fetch or _fetch_vpic
    url = _VPIC_URL.format(vin=vin)
    try:
        body = fetcher(url, timeout)
        parsed = _parse_vpic(vin, body)
    except Exception:
        _logger.debug("vPIC decode failed for %s", vin, exc_info=True)
        return None
    if parsed is None:
        return None
    with _VPIC_LOCK:
        _VPIC_CACHE[vin] = parsed
    return dict(parsed)


def _fetch_vpic(url: str, timeout: float) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "DeavenVinDecoder/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _parse_vpic(vin: str, body: str) -> dict | None:
    payload = json.loads(body)
    results = payload.get("Results") if isinstance(payload, dict) else None
    if not results or not isinstance(results, list):
        return None
    row = results[0]
    if not isinstance(row, dict):
        return None
    return {
        "vin": vin,
        "make": _vpic_text(row.get("Make")),
        "model": _vpic_text(row.get("Model")),
        "model_year": _vpic_year(row.get("ModelYear")),
        "body_class": _vpic_text(row.get("BodyClass")),
        "vehicle_type": _vpic_text(row.get("VehicleType")),
        "plant_city": _vpic_text(row.get("PlantCity")),
        "plant_country": _vpic_text(row.get("PlantCountry")),
        "error_code": _vpic_text(row.get("ErrorCode")),
        "error_text": _vpic_text(row.get("ErrorText")),
    }


def _vpic_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _vpic_year(value: object) -> int | None:
    text = _vpic_text(value)
    if text is not None and text.isdigit():
        return int(text)
    return None
