"""Offline ISO 3779 check-digit tests. No network."""

from __future__ import annotations

import pytest

from shared.vin import VinError, check_digit, is_valid_vin, normalize_vin, validate_vin

# Published examples. Position 9 is the check character, including X for remainder 10.
VALID_DIGIT = "1HGCM82633A004352"
VALID_X = "1M8GDM9AXKP042788"
INVALID_CHECK = "JH4KA8260MC000000"


def test_known_vins_match_their_check_character():
    assert check_digit(VALID_DIGIT) == "3"
    assert validate_vin(VALID_DIGIT) == VALID_DIGIT
    assert check_digit(VALID_X) == "X"
    assert validate_vin(VALID_X) == VALID_X


def test_check_digit_rejects_a_wrong_character():
    with pytest.raises(VinError, match="invalid"):
        validate_vin(INVALID_CHECK)
    assert is_valid_vin(INVALID_CHECK) is False
    assert is_valid_vin(VALID_DIGIT) is True
    assert is_valid_vin(None) is False
    assert is_valid_vin("") is False


def test_normalize_strips_separators_and_lower_case():
    assert normalize_vin(" 1hg-cm82633-a004352 ") == VALID_DIGIT
    assert validate_vin("1hg-cm82633-a004352") == VALID_DIGIT


def test_illegal_characters_and_length():
    with pytest.raises(VinError, match="illegal"):
        validate_vin("1HGCM82633A00435I")
    with pytest.raises(VinError, match="illegal"):
        validate_vin("1HGCM82633A00435O")
    with pytest.raises(VinError, match="illegal"):
        validate_vin("1HGCM82633A00435Q")
    with pytest.raises(VinError, match="17"):
        validate_vin("1HGCM82633A00435")
    with pytest.raises(VinError, match="17"):
        validate_vin("1HGCM82633A0043522")
