"""
Location intelligence for laundromat opportunities.

The service prefers live data sources when reachable:

* **Nominatim** (OpenStreetMap) — free geocoding (1 req/sec).
* **Overpass API** — free POI counts (laundromats, hostels, universities, hotels).

Every call is wrapped in ``httpx`` with a tight timeout and falls back to the
``LocationBaseline`` defaults from :mod:`app.laundry.assumptions` when network
or rate limits get in the way. The pipeline therefore *always* returns useful
numbers — they're just lower-confidence when external lookups fail.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any, Dict, Optional

import httpx
import structlog

from app.laundry.assumptions import default_assumptions

log = structlog.get_logger(__name__)


_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_USER_AGENT = "KUA-Laundry/1.0 (+https://klaveurbanagent.com)"


async def geocode(address: str, *, city: Optional[str] = None) -> Dict[str, Optional[float]]:
    """Return ``{lat, lng}`` for the supplied address (None on failure)."""
    if not address:
        return {"lat": None, "lng": None}
    query = address if not city or city.lower() in address.lower() else f"{address}, {city}"
    try:
        async with httpx.AsyncClient(
            timeout=8.0,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "en"},
        ) as client:
            r = await client.get(
                _NOMINATIM_URL,
                params={"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 0},
            )
            r.raise_for_status()
            data = r.json()
            if not data:
                return {"lat": None, "lng": None}
            return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])}
    except Exception as e:
        log.warning("laundry.geocode_failed", error=str(e), query=query)
        return {"lat": None, "lng": None}


_OVERPASS_TEMPLATE = """
[out:json][timeout:25];
(
  node["shop"="laundry"](around:500,{lat},{lng});
  node["amenity"="laundry"](around:500,{lat},{lng});
);
out count;
"""

_COMPETITION_TEMPLATE = """
[out:json][timeout:25];
(
  node["shop"="laundry"](around:1000,{lat},{lng});
  node["amenity"="laundry"](around:1000,{lat},{lng});
  node["shop"="dry_cleaning"](around:1000,{lat},{lng});
);
out count;
"""

_POI_TEMPLATE = """
[out:json][timeout:25];
(
  node["tourism"~"hotel|hostel|guest_house"](around:500,{lat},{lng});
  node["amenity"="university"](around:2000,{lat},{lng});
  node["amenity"="hospital"](around:1500,{lat},{lng});
  node["military"](around:2500,{lat},{lng});
);
out count;
"""


def _haversine_km(a: Dict[str, float], b: Dict[str, float]) -> float:
    R = 6371.0
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlng = math.radians(b["lng"] - a["lng"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


async def _overpass_count(query: str) -> int:
    try:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": _USER_AGENT}) as client:
            r = await client.post(_OVERPASS_URL, data={"data": query})
            r.raise_for_status()
            data = r.json()
            elements = data.get("elements") or []
            for el in elements:
                tags = el.get("tags") or {}
                if "total" in tags:
                    try:
                        return int(tags["total"])
                    except (TypeError, ValueError):
                        continue
            return len(elements)
    except Exception as e:
        log.warning("laundry.overpass_failed", error=str(e))
        return -1


def _match_preferred_market(
    *,
    neighbourhood: Optional[str],
    city: Optional[str],
    address: Optional[str] = None,
) -> Optional[str]:
    """Return the first preferred-neighbourhood label (case-insensitive substring)
    that appears in any of the location fields, or ``None``."""
    biz = default_assumptions().business_profile
    haystack = " ".join(
        s for s in (neighbourhood, city, address) if s
    ).lower()
    if not haystack:
        return None
    for label in biz.preferred_neighbourhoods:
        if label.lower() in haystack:
            return label
    return None


async def gather_location_intel(
    *,
    lat: Optional[float],
    lng: Optional[float],
    neighbourhood: Optional[str] = None,
    city: Optional[str] = None,
    address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pull the location signals required by the scoring engine.

    Always returns the full set of keys — missing live data is replaced by the
    ``LocationBaseline`` defaults so the scoring engine never has to guess.
    Also flags whether the property is inside one of the operator's preferred
    Barcelona target markets (Raval, Sant Antoni, Poble Sec, Clot, Hospitalet).
    """
    baseline = default_assumptions().location_baseline
    biz = default_assumptions().business_profile

    matched = _match_preferred_market(neighbourhood=neighbourhood, city=city, address=address)

    intel: Dict[str, Any] = {
        "population_density_per_km2": baseline.population_density_per_km2,
        "apartment_density_pct": baseline.apartment_density_pct,
        "household_income_eur": baseline.median_household_income_eur,
        "students_within_1km": baseline.students_within_1km,
        "hotels_within_500m": baseline.hotels_within_500m,
        "universities_within_2km": baseline.universities_within_2km,
        "nearby_laundromats_within_500m": baseline.nearby_laundromats_within_500m,
        "competitors_within_1km": baseline.competitors_within_1km,
        "walkability_score_0_100": baseline.walkability_score_0_100,
        "night_safety_0_100": baseline.night_safety_0_100,
        "growth_potential_0_100": 70 if matched else 62,
        "street_visibility_0_100": 70,
        "public_transport_score_0_100": 75 if matched else 72,
        "data_sources": [],
        "neighbourhood": neighbourhood,
        "city": city,
        "in_preferred_market": bool(matched),
        "matched_preferred_neighbourhood": matched,
        "target_city": biz.target_city,
        "preferred_neighbourhoods": list(biz.preferred_neighbourhoods),
    }

    if lat is None or lng is None:
        intel["data_sources"].append("baseline_only")
        return intel

    laundro_500m, competitors_1km, poi_counts = await asyncio.gather(
        _overpass_count(_OVERPASS_TEMPLATE.format(lat=lat, lng=lng)),
        _overpass_count(_COMPETITION_TEMPLATE.format(lat=lat, lng=lng)),
        _overpass_count(_POI_TEMPLATE.format(lat=lat, lng=lng)),
        return_exceptions=False,
    )

    if laundro_500m >= 0:
        intel["nearby_laundromats_within_500m"] = laundro_500m
        intel["data_sources"].append("overpass:laundro_500m")
    if competitors_1km >= 0:
        intel["competitors_within_1km"] = competitors_1km
        intel["data_sources"].append("overpass:competitors_1km")
    if poi_counts >= 0:
        # We requested hotels, universities, hospitals, military — Overpass returns the union
        # count; we use it as a coarse "destination intensity" proxy.
        intel["destination_intensity"] = poi_counts
        intel["data_sources"].append("overpass:poi")

    return intel
