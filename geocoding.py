"""Shared geocoding for storage + laundry verticals.

Provider chain (first success wins):
  1. Google Geocoding API  — requires ``GOOGLE_API_KEY``
  2. Nominatim (OpenStreetMap)
  3. Neighbourhood + city query
  4. City centre fallback (approximate)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

import requests

log = logging.getLogger("kua.geocoding")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "kua-acquisition/2.1 (contact: ops@kua.app)"
TIMEOUT_SEC = 12.0

BARCELONA_CENTER: Tuple[float, float] = (41.3874, 2.1686)
CITY_CENTroids: Dict[str, Tuple[float, float]] = {
    "barcelona": BARCELONA_CENTER,
    "l'hospitalet": (41.3598, 2.0994),
    "hospitalet": (41.3598, 2.0994),
}


def geocoding_status() -> Dict[str, Any]:
    return {
        "google_api_key_configured": bool(GOOGLE_API_KEY),
        "provider_chain": ["google", "nominatim", "neighbourhood", "city_default"],
    }


def _google_geocode(query: str) -> Optional[Tuple[float, float]]:
    if not GOOGLE_API_KEY or not query.strip():
        return None
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": query, "key": GOOGLE_API_KEY},
            timeout=TIMEOUT_SEC,
        )
        data = r.json()
        if data.get("status") != "OK":
            log.info("google.geocode status=%s query=%s", data.get("status"), query[:80])
            return None
        loc = (data.get("results") or [{}])[0].get("geometry", {}).get("location") or {}
        lat, lng = loc.get("lat"), loc.get("lng")
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)
    except Exception as exc:
        log.warning("google.geocode failed query=%s: %s", query[:80], exc)
        return None


def _nominatim_geocode(query: str) -> Optional[Tuple[float, float]]:
    if not query.strip():
        return None
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "addressdetails": 0},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SEC,
        )
        r.raise_for_status()
        rows = r.json() or []
        if not rows:
            return None
        return float(rows[0]["lat"]), float(rows[0]["lon"])
    except Exception as exc:
        log.warning("nominatim.geocode failed query=%s: %s", query[:80], exc)
        return None


def _city_centroid(city: Optional[str]) -> Optional[Tuple[float, float]]:
    key = (city or "Barcelona").strip().lower()
    return CITY_CENTroids.get(key) or BARCELONA_CENTER


def resolve_coordinates(
    *,
    address: Optional[str] = None,
    city: Optional[str] = None,
    neighbourhood: Optional[str] = None,
    allow_city_default: bool = True,
) -> Tuple[Optional[float], Optional[float], str]:
    """Return ``(lat, lng, source)`` using the provider chain."""
    city = (city or "Barcelona").strip()
    queries: list[tuple[str, str]] = []

    if address and address.strip():
        queries.append((f"{address.strip()}, {city}, Spain", "google"))
    if neighbourhood and neighbourhood.strip():
        queries.append((f"{neighbourhood.strip()}, {city}, Spain", "neighbourhood"))
    if city:
        queries.append((f"{city}, Spain", "city"))

    for query, label in queries:
        coords = _google_geocode(query)
        if coords:
            log.info("geocode ok source=google label=%s query=%s", label, query[:80])
            return coords[0], coords[1], "google"

    for query, label in queries:
        coords = _nominatim_geocode(query)
        if coords:
            log.info("geocode ok source=nominatim label=%s query=%s", label, query[:80])
            return coords[0], coords[1], "nominatim"

    if allow_city_default:
        lat, lng = _city_centroid(city)
        log.info("geocode fallback source=city_default city=%s", city)
        return lat, lng, "city_default"

    return None, None, "none"


def geocode_address(address: str) -> Dict[str, Optional[float]]:
    """Back-compat wrapper used by storage ``location.py`` and ``main.py``."""
    lat, lng, _source = resolve_coordinates(address=address, city="Barcelona")
    return {"lat": lat, "lng": lng}
