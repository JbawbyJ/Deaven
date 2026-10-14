"""ISO 3779 VIN check-digit validation.

The risk agent decodes VINs through NHTSA. This module is the offline
check used before a VIN may identify a listing. It does not call the network.
"""

from __future__ import annotations

import re

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
