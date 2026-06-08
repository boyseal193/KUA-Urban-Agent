"""Independent location intelligence using public APIs (Nominatim + Overpass).

All HTTP is via the ``requests`` library which is already a hard dependency of
the storage stack. Failures are tolerated — we fall back to the baseline
assumptions instead of crashing the underwriting pipeline.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

import requests

from laundry.assumptions import default_assumptions

log = logging.getLogger("kua.laundry.location")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "kua-laundry-acquisition/2.0 (contact: ops@kua.app)"
TIMEOUT_SEC = 12.0


PREFERRED_MARKETS = {
    "raval": "Raval",
    "sant antoni": "Sant Antoni",
    "poble sec": "Poble Sec",
    "clot": "Clot",
    "hospitalet": "L'Hospitalet",
    "l'hospitalet": "L'Hospitalet",
    "lhospitalet": "L'Hospitalet",
}


def _match_preferred_market(*, neighbourhood: Optional[str], address: Optional[str],
                              city: Optional[str]) -> Optional[str]:
    haystacks = [neighbourhood or "", address or "", city or ""]
    blob = " ".join(haystacks).lower()
    for needle, label in PREFERRED_MARKETS.items():
        if needle in blob:
            return label
    return None


def geocode(address: str, *, city: str = "Barcelona") -> Optional[Tuple[float, float]]:
    if not address:
        return None
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": f"{address}, {city}", "format": "json", "limit": 1, "addressdetails": 0},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SEC,
        )
        r.raise_for_status()
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:  # pragma: no cover — network
        log.warning("Geocode failed for %s: %s", address, exc)
    return None


def _overpass_count(lat: float, lng: float, radius_m: int, filter_str: str) -> int:
    query = f"""
[out:json][timeout:25];
(
  node[{filter_str}](around:{radius_m},{lat},{lng});
  way[{filter_str}](around:{radius_m},{lat},{lng});
);
out count;
""".strip()
    try:
        r = requests.post(OVERPASS_URL, data={"data": query},
                          headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SEC)
        r.raise_for_status()
        data = r.json()
        elements = data.get("elements") or []
        if elements and "tags" in elements[0]:
            total = elements[0]["tags"].get("total")
            try: return int(total)
            except (TypeError, ValueError): return 0
    except Exception as exc:  # pragma: no cover — network
        log.warning("Overpass query failed: %s", exc)
    return 0


def gather_location_intel(*, lat: Optional[float], lng: Optional[float],
                            address: Optional[str], city: Optional[str],
                            neighbourhood: Optional[str]) -> Dict[str, Any]:
    baseline = default_assumptions().location_baseline
    matched = _match_preferred_market(neighbourhood=neighbourhood, address=address, city=city)

    intel: Dict[str, Any] = {
        "lat": lat, "lng": lng,
        "city": city or "Barcelona",
        "neighbourhood": neighbourhood,
        "matched_preferred_neighbourhood": matched,
        "in_preferred_market": bool(matched),
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
        "street_visibility_0_100": 65,
        "growth_potential_0_100": 65,
        "public_transport_score_0_100": 75,
    }

    if lat is None or lng is None:
        intel["data_source"] = "baseline_only"
        return intel

    try:
        intel["nearby_laundromats_within_500m"] = _overpass_count(lat, lng, 500, "shop=laundry")
        intel["competitors_within_1km"] = max(
            _overpass_count(lat, lng, 1000, "shop=laundry"),
            intel["nearby_laundromats_within_500m"],
        )
        intel["hotels_within_500m"] = _overpass_count(lat, lng, 500, "tourism=hotel")
        intel["universities_within_2km"] = _overpass_count(lat, lng, 2000, "amenity=university")
        intel["data_source"] = "overpass"
    except Exception as exc:  # pragma: no cover
        log.warning("Live location intel failed: %s", exc)
        intel["data_source"] = "baseline_only"

    return intel
