"""
Fixture listings for the local scout.

Swap this module (or SCOUT_BACKEND=live) when real scrapers are wired.
URLs are synthetic so ingest can be demoed without hitting live sites.
"""

from __future__ import annotations

from typing import Any

# Slug is the local:// identifier accepted by POST /deals/ingest
CATALOG: list[dict[str, Any]] = [
    {
        "slug": "bmw-m3-2003",
        "source": "bat",
        "url": "https://bringatrailer.com/listing/2003-bmw-m3-e46-deaven-demo",
        "title": "2003 BMW M3 Coupe",
        "price": 28900,
        "market_avg": 42000,
        "mileage": 62140,
        "year": 2003,
        "make": "BMW",
        "model": "M3",
        "trim": "Coupe",
        "location": "Austin, TX",
        "description": "One-owner E46 M3, stock exhaust, recent cooling-system work.",
        "seller_type": "private",
        "watch_count": 214,
        "bid_count": 18,
        "color_ext": "Silver Grey",
        "color_int": "Black",
        "transmission": "6-speed manual",
        "drivetrain": "RWD",
        "images": [],
        "condition_hint": 82.0,
        "provenance_hint": 78.0,
        "demand_hint": 88.0,
    },
    {
        "slug": "rx7-1993",
        "source": "ebay",
        "url": "https://www.ebay.com/itm/deaven-demo-1993-mazda-rx7",
        "title": "1993 Mazda RX-7 Touring",
        "price": 32500,
        "market_avg": 41000,
        "mileage": 78400,
        "year": 1993,
        "make": "Mazda",
        "model": "RX-7",
        "trim": "Touring",
        "location": "Portland, OR",
        "description": "FD3S Touring, compression recently tested, no known apex-seal issues.",
        "seller_type": "private",
        "watch_count": 96,
        "color_ext": "Vintage Red",
        "color_int": "Tan",
        "transmission": "5-speed manual",
        "drivetrain": "RWD",
        "images": [],
        "condition_hint": 74.0,
        "provenance_hint": 68.0,
        "demand_hint": 80.0,
    },
    {
        "slug": "911-2004",
        "source": "classic_com",
        "url": "https://www.classic.com/veh/deaven-demo-2004-porsche-911",
        "title": "2004 Porsche 911 Carrera",
        "price": 41000,
        "market_avg": 44000,
        "mileage": 91200,
        "year": 2004,
        "make": "Porsche",
        "model": "911",
        "trim": "Carrera",
        "location": "Denver, CO",
        "description": "996 Carrera cabriolet, IMS updated, books and records from 2012 on.",
        "seller_type": "dealer",
        "watch_count": 41,
        "color_ext": "Seal Grey",
        "color_int": "Black",
        "transmission": "6-speed manual",
        "drivetrain": "RWD",
        "images": [],
        "condition_hint": 70.0,
        "provenance_hint": 64.0,
        "demand_hint": 62.0,
    },
    {
        "slug": "supra-1998",
        "source": "tcv",
        "url": "https://www.tc-v.com/stock/deaven-demo-1998-toyota-supra",
        "title": "1998 Toyota Supra SZ-R",
        "price": 62000,
        "market_avg": 95000,
        "mileage": 54300,
        "year": 1998,
        "make": "Toyota",
        "model": "Supra",
        "trim": "SZ-R",
        "location": "Japan",
        "description": "JDM SZ-R, auction grade 4, complete service file, 25-year eligible.",
        "seller_type": "dealer",
        "watch_count": 180,
        "color_ext": "Super White",
        "color_int": "Black",
        "transmission": "6-speed manual",
        "drivetrain": "RWD",
        "images": [],
        "condition_hint": 86.0,
        "provenance_hint": 80.0,
        "demand_hint": 92.0,
    },
    {
        "slug": "s2000-2006",
        "source": "hemmings",
        "url": "https://www.hemmings.com/listing/deaven-demo-2006-honda-s2000",
        "title": "2006 Honda S2000",
        "price": 24500,
        "market_avg": 24000,
        "mileage": 118500,
        "year": 2006,
        "make": "Honda",
        "model": "S2000",
        "trim": "AP2",
        "location": "Atlanta, GA",
        "description": "High-mileage AP2, aftermarket exhaust, soft top recently replaced.",
        "seller_type": "private",
        "watch_count": 12,
        "color_ext": "Suzuka Blue",
        "color_int": "Black",
        "transmission": "6-speed manual",
        "drivetrain": "RWD",
        "images": [],
        "condition_hint": 62.0,
        "provenance_hint": 62.0,
        "demand_hint": 55.0,
    },
]


def get_by_slug(slug: str) -> dict[str, Any] | None:
    key = slug.strip().lower().removeprefix("local://")
    for item in CATALOG:
        if item["slug"] == key:
            return item
    return None


def get_by_url(url: str) -> dict[str, Any] | None:
    normalized = url.strip().rstrip("/").lower()
    for item in CATALOG:
        if item["url"].rstrip("/").lower() == normalized:
            return item
        if item["slug"] in normalized:
            return item
    return None


def match_filters(item: dict[str, Any], filters: Any) -> bool:
    """Apply WatchlistFilter-like attributes to a catalog row."""
    make = (item.get("make") or "").lower()
    model = (item.get("model") or "").lower()
    title = (item.get("title") or "").lower()
    price = float(item.get("price") or 0)
    year = item.get("year")

    makes = [m.lower() for m in getattr(filters, "makes", []) or []]
    models = [m.lower() for m in getattr(filters, "models", []) or []]
    if makes and not any(m in make or m in title for m in makes):
        return False
    if models and not any(m in model or m in title for m in models):
        return False
    price_min = getattr(filters, "price_min", None)
    price_max = getattr(filters, "price_max", None)
    year_min = getattr(filters, "year_min", None)
    year_max = getattr(filters, "year_max", None)
    mileage_max = getattr(filters, "mileage_max", None)
    if price_min is not None and price < price_min:
        return False
    if price_max is not None and price > price_max:
        return False
    if year_min and year and year < year_min:
        return False
    if year_max and year and year > year_max:
        return False
    if mileage_max and item.get("mileage") and item["mileage"] > mileage_max:
        return False
    return True
