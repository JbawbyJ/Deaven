"""Offline tests for shared.vin. Network calls are marked and deselected by default."""

from __future__ import annotations

import json
from datetime import date

import pytest

from shared.schemas.deal import DealPayload, DealSource, ListingData
from shared.vin import (
    VinDecode,
    clear_vpic_cache,
    decode_vin,
    decode_vpic,
    normalize_vin,
    validate_check_digit,
    vin_key,
    vpic_enabled,
)

# Check digits below were computed from the ISO 3779 / 49 CFR 565 weights,
# independently of shared.vin.
HONDA_US = "1HGCM82633A004352"  # pos 7 numeric, year code 3
HONDA_US_BAD_CHECK = "1HGCM82603A004352"
FORD_1980 = "1FABP1AA7AA000001"  # pos 7 letter, year code A
FORD_2010 = "1FABP12A9AA000001"  # pos 7 digit, year code A
FORD_2009 = "1FABP1AA29A000001"  # pos 7 letter, year code 9
FORD_2039 = "1FABP12A49A000001"  # pos 7 digit, year code 9
FORD_2000 = "1FABP1AA4YA000001"  # pos 7 letter, year code Y
FORD_2030 = "1FABP12A6YA000001"  # pos 7 digit, year code Y
FORD_YEAR_U = "1FABP1AA1UA000001"
FORD_YEAR_0 = "1FABP1AA90A000001"
FORD_YEAR_Z = "1FABP1AA2ZA000001"
CHECK_DIGIT_X = "1G1YY2AGXX5000001"
BMW_YEAR_9 = "WBAWB31019P123456"  # pos 7 digit, year code 9, not North American
BMW_YEAR_A = "WBAWB3A06AP123456"  # pos 7 letter, year code A
BMW_YEAR_T = "WBAWB3102TP123456"
PORSCHE = "WP0ZZZ998TS392124"
HONDA_JP = "JHMCM56557C404453"
HONDA_CA = "2HGES16525H123456"
VW_BR = "9BWZZZ3X5T1234567"
FORD_AU = "6FPAAAJG5S1234567"
VW_MX = "3VWDP7AJ0EM123456"
AS_OF = date(2026, 10, 14)


@pytest.fixture(autouse=True)
def _reset_vpic_cache():
    clear_vpic_cache()
    yield
    clear_vpic_cache()


def test_normalize_uppercases_and_strips_space_and_dashes():
    assert normalize_vin("  1hg-cm82633-a004352  ") == HONDA_US
    assert normalize_vin("1HG CM82633 A004352") == HONDA_US
    assert normalize_vin("1HG-CM-82633-A004352") == HONDA_US
    assert normalize_vin(HONDA_US) == HONDA_US


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "---",
        12345678901234567,
        HONDA_US[:16],
        HONDA_US + "X",
        "1HGCM82633A00435I",
        "1HGCM82633A00435O",
        "1HGCM82633A00435Q",
        "ihgcm82633a004352",
        "OHGCM82633A004352",
        "1HGCM82633A00435*",
        "1HGCM82633A00435!",
    ],
)
def test_normalize_rejects_length_ioq_and_non_vin_characters(raw):
    assert normalize_vin(raw) is None


def test_check_digit_accepts_real_vins_including_x():
    assert validate_check_digit(HONDA_US) is True
    assert validate_check_digit("1hg-cm82633-a004352") is True
    assert validate_check_digit(CHECK_DIGIT_X) is True
    assert validate_check_digit(FORD_1980) is True
    assert validate_check_digit(PORSCHE) is True


def test_check_digit_mismatch_is_information_not_a_reject():
    assert validate_check_digit(HONDA_US_BAD_CHECK) is False
    decoded = decode_vin(HONDA_US_BAD_CHECK)
    assert isinstance(decoded, VinDecode)
    assert decoded.vin == HONDA_US_BAD_CHECK
    assert decoded.check_digit == "0"
    assert decoded.check_digit_expected == "3"
    assert decoded.check_digit_valid is False
    assert decoded.check_digit_applicable is True
    assert decoded.manufacturer == "Honda"
    assert validate_check_digit(None) is None
    assert validate_check_digit("TOO-SHORT") is None


def test_north_american_check_digit_is_applicable_outside_it_is_not():
    us = decode_vin(HONDA_US)
    canada = decode_vin(HONDA_CA)
    mexico = decode_vin(VW_MX)
    germany = decode_vin(PORSCHE)
    assert us.check_digit_applicable is True
    assert canada.check_digit_applicable is True
    assert mexico.check_digit_applicable is True
    assert germany.check_digit_applicable is False
    assert germany.check_digit_valid is True


def test_honda_us_offline_decode():
    decoded = decode_vin(f" {HONDA_US.lower()} ")
    assert decoded.vin == HONDA_US
    assert decoded.wmi == "1HG"
    assert decoded.region == "North America"
    assert decoded.country == "United States"
    assert decoded.manufacturer == "Honda"
    assert decoded.plant_code == "A"
    assert decoded.serial == "004352"
    assert decoded.model_year_candidates == (2003, 2033)
    # Position 7 is numeric, so 49 CFR 565 selects the 2010–2039 cycle.
    assert decoded.model_year == 2033
    assert decoded.model_year_source == "north_america_position_7"


@pytest.mark.parametrize(
    ("vin", "year", "candidates"),
    [
        (FORD_1980, 1980, (1980, 2010)),
        (FORD_2010, 2010, (1980, 2010)),
        (FORD_2009, 2009, (2009, 2039)),
        (FORD_2039, 2039, (2009, 2039)),
        (FORD_2000, 2000, (2000, 2030)),
        (FORD_2030, 2030, (2000, 2030)),
    ],
)
def test_north_american_model_year_cycle_edges(vin, year, candidates):
    decoded = decode_vin(vin, as_of=date(2030, 1, 1))
    assert decoded.model_year == year
    assert decoded.model_year_candidates == candidates
    assert decoded.model_year_source == "north_america_position_7"
    assert decoded.region == "North America"
    assert decoded.check_digit_valid is True


def test_position_7_hint_does_not_move_a_letter_vin_onto_the_later_cycle():
    decoded = decode_vin(FORD_1980, as_of=date(2026, 6, 1))
    assert decoded.model_year == 1980


def test_invalid_model_year_codes_stay_unknown():
    for vin in (FORD_YEAR_U, FORD_YEAR_0, FORD_YEAR_Z):
        decoded = decode_vin(vin)
        assert decoded is not None
        assert decoded.model_year is None
        assert decoded.model_year_candidates == ()
        assert decoded.model_year_source == "invalid_year_code"
        assert decoded.check_digit_valid is True


def test_non_north_american_year_ignores_position_7_and_avoids_far_future():
    later_cycle_by_position_7 = decode_vin(BMW_YEAR_9, as_of=AS_OF)
    assert later_cycle_by_position_7.region == "Europe"
    assert later_cycle_by_position_7.country == "Germany"
    assert later_cycle_by_position_7.manufacturer == "BMW"
    assert later_cycle_by_position_7.wmi == "WBA"
    assert later_cycle_by_position_7.model_year_candidates == (2009, 2039)
    assert later_cycle_by_position_7.model_year == 2009
    assert later_cycle_by_position_7.model_year_source == "latest_not_after_next_model_year"
    assert later_cycle_by_position_7.check_digit_applicable is False

    early_cycle_by_position_7 = decode_vin(BMW_YEAR_A, as_of=AS_OF)
    assert early_cycle_by_position_7.model_year_candidates == (1980, 2010)
    assert early_cycle_by_position_7.model_year == 2010


def test_non_north_american_year_horizon_edges():
    current = decode_vin(BMW_YEAR_T, as_of=date(2026, 10, 14))
    assert current.model_year_candidates == (1996, 2026)
    assert current.model_year == 2026

    # The later cycle is kept when it is the next model year (as_of.year + 1).
    next_model_year = decode_vin(BMW_YEAR_T, as_of=date(2025, 1, 1))
    assert next_model_year.model_year == 2026

    too_far_ahead = decode_vin(BMW_YEAR_T, as_of=date(2024, 6, 1))
    assert too_far_ahead.model_year == 1996

    both_in_range = decode_vin(BMW_YEAR_T, as_of=date(2030, 1, 1))
    assert both_in_range.model_year == 2026


def test_region_country_manufacturer_and_vis_fields():
    porsche = decode_vin(PORSCHE, as_of=AS_OF)
    assert porsche.manufacturer == "Porsche"
    assert porsche.region == "Europe"
    assert porsche.country == "Germany"
    assert porsche.plant_code == "S"
    assert porsche.serial == "392124"
    assert porsche.model_year == 2026

    japan = decode_vin(HONDA_JP, as_of=AS_OF)
    assert japan.manufacturer == "Honda"
    assert japan.region == "Asia"
    assert japan.country == "Japan"
    assert japan.plant_code == "C"
    assert japan.serial == "404453"
    assert japan.model_year == 2007
    assert japan.check_digit_applicable is False

    canada = decode_vin(HONDA_CA)
    assert canada.manufacturer == "Honda"
    assert canada.country == "Canada"

    mexico = decode_vin(VW_MX)
    assert mexico.manufacturer == "Volkswagen"
    assert mexico.country == "Mexico"

    brazil = decode_vin(VW_BR, as_of=AS_OF)
    assert brazil.manufacturer == "Volkswagen"
    assert brazil.region == "South America"
    assert brazil.country == "Brazil"

    australia = decode_vin(FORD_AU)
    assert australia.manufacturer == "Ford"
    assert australia.region == "Oceania"
    assert australia.country == "Australia"

    africa = decode_vin("AA1AAAAAAA0000001")
    assert africa.region == "Africa"
    assert africa.country == "South Africa"
    assert africa.manufacturer is None

    jaguar = decode_vin("SAJAA1234A1234567")
    assert jaguar.manufacturer == "Jaguar"
    assert jaguar.country == "United Kingdom"

    hyundai = decode_vin("KMHCT41AE0U123456")
    assert hyundai.manufacturer == "Hyundai"
    assert hyundai.region == "Asia"
    assert hyundai.country == "South Korea"

    volvo = decode_vin("YV1TS92DX0X123456")
    assert volvo.manufacturer == "Volvo"
    assert volvo.country == "Sweden"


def test_unknown_wmi_still_decodes_structure():
    decoded = decode_vin("1ZZAA11A0AA000001")
    assert decoded.manufacturer is None
    assert decoded.region == "North America"
    assert decoded.country == "United States"
    assert decoded.wmi == "1ZZ"
    assert len(decoded.serial) == 6
    assert len(decoded.plant_code) == 1


def test_decode_returns_none_for_unusable_input():
    assert decode_vin(None) is None
    assert decode_vin("1HGCM82633A00435I") is None
    assert decode_vin("short") is None


def test_vin_key_is_stable_across_source_formatting():
    assert vin_key(HONDA_US) == HONDA_US
    assert vin_key("1hg-cm82633-a004352") == vin_key("1HG CM82633 A004352")
    assert vin_key(" 1hgcm82633a004352 ") == HONDA_US
    assert vin_key(HONDA_US) != vin_key(HONDA_US_BAD_CHECK)
    assert vin_key(HONDA_US_BAD_CHECK) == HONDA_US_BAD_CHECK
    assert vin_key(None) is None
    assert vin_key("not a vin") is None
    assert vin_key(PORSCHE) != vin_key(HONDA_US)


def test_listing_schema_normalizes_vin_and_drops_unusable_values():
    normalized = ListingData(title="Accord", price=4200, vin="1hg-cm82633-a004352")
    assert normalized.vin == HONDA_US

    absent = ListingData(title="No vin", price=1)
    assert absent.vin is None
    blank = ListingData(title="Blank", price=1, vin="  ")
    assert blank.vin is None
    rejected = ListingData(title="Bad", price=1, vin="NOT-A-VIN")
    assert rejected.vin is None

    payload = DealPayload(
        source=DealSource.MANUAL,
        url="https://example.test/accord",
        listing=ListingData(title="Accord", price=4200, vin="1HG CM82633 A004352"),
    )
    assert payload.listing.vin == HONDA_US
    restored = DealPayload.model_validate(payload.model_dump())
    assert restored.listing.vin == HONDA_US


def test_vpic_is_off_unless_enabled_and_sends_no_credentials(monkeypatch):
    monkeypatch.delenv("VIN_VPIC_ENABLED", raising=False)
    assert vpic_enabled() is False

    def explode(url, timeout):
        raise AssertionError(f"fetch should not run for {url}")

    assert decode_vpic(HONDA_US, fetch=explode) is None
    assert decode_vpic("not-a-vin", enabled=True, fetch=explode) is None

    monkeypatch.setenv("VIN_VPIC_ENABLED", "true")
    assert vpic_enabled() is True
    assert decode_vpic(HONDA_US, enabled=False, fetch=explode) is None

    seen = {}

    def fetch(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout
        return json.dumps(
            {
                "Results": [
                    {
                        "Make": "HONDA",
                        "Model": "Accord",
                        "ModelYear": "2003",
                        "BodyClass": "Sedan/Saloon",
                        "VehicleType": "PASSENGER CAR",
                        "PlantCity": "MARYSVILLE",
                        "PlantCountry": "UNITED STATES (USA)",
                        "ErrorCode": "0",
                        "ErrorText": "",
                    }
                ]
            }
        )

    decoded = decode_vpic("1hg-cm82633-a004352", enabled=True, timeout=2.5, fetch=fetch)
    assert seen["timeout"] == 2.5
    assert seen["url"].startswith("https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/")
    assert HONDA_US in seen["url"]
    assert "format=json" in seen["url"]
    assert "api_key" not in seen["url"]
    assert "token=" not in seen["url"]
    assert decoded == {
        "vin": HONDA_US,
        "make": "HONDA",
        "model": "Accord",
        "model_year": 2003,
        "body_class": "Sedan/Saloon",
        "vehicle_type": "PASSENGER CAR",
        "plant_city": "MARYSVILLE",
        "plant_country": "UNITED STATES (USA)",
        "error_code": "0",
        "error_text": None,
    }


def test_vpic_caches_success_and_fails_soft_on_errors():
    calls = {"n": 0}

    def fetch(url, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("vpic timed out")
        return json.dumps({"Results": [{"Make": "FORD", "Model": "Mustang", "ModelYear": ""}]})

    assert decode_vpic(FORD_2010, enabled=True, fetch=fetch) is None
    decoded = decode_vpic(FORD_2010, enabled=True, fetch=fetch)
    assert decoded["make"] == "FORD"
    assert decoded["model"] == "Mustang"
    assert decoded["model_year"] is None
    again = decode_vpic("1fabp12a9aa000001", enabled=True, fetch=fetch)
    assert again["make"] == "FORD"
    assert calls["n"] == 2

    def bad_json(url, timeout):
        return "not-json"

    assert decode_vpic(HONDA_US, enabled=True, fetch=bad_json) is None


def test_settings_toggle_matches_vpic_env(monkeypatch):
    from backend.core.settings import vin_vpic_enabled

    monkeypatch.delenv("VIN_VPIC_ENABLED", raising=False)
    assert vin_vpic_enabled() is False
    monkeypatch.setenv("VIN_VPIC_ENABLED", "on")
    assert vin_vpic_enabled() is True
    assert vpic_enabled() is True


@pytest.mark.network
def test_vpic_live_public_decode():
    """Calls the public NHTSA vPIC API. Deselected unless pytest is run with -m network."""
    decoded = decode_vpic(HONDA_US, enabled=True, timeout=15)
    assert decoded is not None
    assert str(decoded["make"]).upper() == "HONDA"
