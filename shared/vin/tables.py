"""Static ISO 3779 / 49 CFR 565 tables. Not the full WMI registry."""

from __future__ import annotations

# Values used by the check-digit transliteration (49 CFR 565.15).
TRANSLITERATION: dict[str, int] = {
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

# Position weights. Position 9 (the check digit) has weight 0.
WEIGHTS: tuple[int, ...] = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)

# Position 10. The same code repeats every 30 years: (1980-2009, 2010-2039).
# U, Z, and 0 are not year codes. I, O, and Q cannot appear in a VIN.
YEAR_CODES: dict[str, tuple[int, int]] = {
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

_REGION_GROUPS: tuple[tuple[str, str], ...] = (
    ("ABCDEFGH", "Africa"),
    ("JKLMNPR", "Asia"),
    ("STUVWXYZ", "Europe"),
    ("12345", "North America"),
    ("67", "Oceania"),
    ("89", "South America"),
)

REGIONS: dict[str, str] = {
    char: name for chars, name in _REGION_GROUPS for char in chars
}


def _countries() -> dict[str, str]:
    """ISO 3780-style country codes from VIN positions 1-2.

    Unlisted pairs stay unknown rather than being guessed.
    """
    table: dict[str, str] = {}

    def assign(first: str, seconds: str, country: str) -> None:
        for char in seconds:
            table[first + char] = country

    vin = "0123456789ABCDEFGHJKLMNPRSTUVWXYZ"
    for first, country in (
        ("1", "United States"),
        ("4", "United States"),
        ("5", "United States"),
        ("2", "Canada"),
        ("J", "Japan"),
        ("L", "China"),
        ("W", "Germany"),
    ):
        assign(first, vin, country)

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


COUNTRIES: dict[str, str] = _countries()

# Three-character WMI → make. Common passenger-vehicle codes only.
MANUFACTURERS: dict[str, str] = {
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
