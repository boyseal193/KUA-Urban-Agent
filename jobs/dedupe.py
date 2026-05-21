"""Property deduplication primitives.

Strategy
--------
Every property has a deterministic ``dedupe_key`` derived from the strongest
identifying signal available at extraction time, in priority order:

1. **Canonical Idealista property ID** parsed from ``listing_url``.
   ``https://www.idealista.com/inmueble/12345678/`` → ``idealista:12345678``.
   This is the most reliable signal — same URL, same property.

2. **Normalized address + city**. Lowercased, accent-stripped, whitespace
   collapsed, street type words (calle/carrer/avinguda/c.) folded so
   "Carrer del Carme 10, Barcelona" and "carrer carme 10 barcelona" hash to
   the same key.

3. **Geographic centroid** rounded to ~10m (4 decimal places of lat/lng).
   Last-resort fallback when no address is present.

The first signal that resolves to a non-empty value wins. The resulting key
is hashed to keep the value short and printable.

Why a deterministic key beats a similarity-graph approach
---------------------------------------------------------
* The Supabase unique partial index ``idx_properties_dedupe_key_active``
  enforces it at the database level — race-free, no application logic
  needed for the hot path.
* Two concurrent scans cannot insert the same property even if they reach
  the INSERT statement at the exact same millisecond — the second one
  gets a PostgreSQL unique-violation and we UPDATE instead of INSERT.
* No model dependency, no embeddings, no ANN index to maintain.

The fuzzier signals (description similarity, AI semantic) are still useful
for the periodic ``cleanup_duplicates`` job that detects misses post-hoc,
but they are not on the insert-path critical path.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------
DEDUPE_KEY_VERSION = "v1"


def parse_idealista_property_id(url: Optional[str]) -> Optional[str]:
    """Return the numeric Idealista property id from a listing URL.

    >>> parse_idealista_property_id("https://www.idealista.com/inmueble/12345678/")
    '12345678'
    >>> parse_idealista_property_id("https://idealista.com/en/inmueble/99/foo")
    '99'
    >>> parse_idealista_property_id(None) is None
    True
    """
    if not url or not isinstance(url, str):
        return None
    m = re.search(r"/inmueble/(\d+)", url)
    if m:
        return m.group(1)
    # Some pages use /pisos-en-venta-... — fall back to any trailing numeric id.
    m = re.search(r"/(\d{6,})(?:/|$)", url)
    if m:
        return m.group(1)
    return None


_STREET_PREFIXES = {
    "calle", "carrer", "avenida", "avinguda", "av", "avd", "avda",
    "carretera", "ctra", "ronda", "passeig", "paseo", "plaza", "placa",
    "plaça", "c", "c.", "c/", "ca", "carrerada",
}


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_address(address: Optional[str]) -> str:
    """Return a lowercased, accent-stripped, prefix-folded address.

    >>> normalize_address("Carrer del Carme 10")
    'carme 10'
    >>> normalize_address("Plaça de Catalunya, 5")
    'catalunya 5'
    >>> normalize_address("  Calle  MAYOR,  3-B ")
    'mayor 3-b'
    """
    if not address or not isinstance(address, str):
        return ""
    text = _strip_accents(address.lower())
    text = re.sub(r"[,;]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = [t for t in text.split(" ") if t]
    # Drop leading street-type prefix tokens.
    while tokens and tokens[0].rstrip(".") in _STREET_PREFIXES:
        tokens.pop(0)
    # Drop generic connector tokens at the start.
    while tokens and tokens[0] in {"de", "del", "dels", "la", "el", "les", "los", "los", "of", "the"}:
        tokens.pop(0)
    return " ".join(tokens)


def normalize_city(city: Optional[str]) -> str:
    if not city or not isinstance(city, str):
        return ""
    return re.sub(r"\s+", " ", _strip_accents(city.lower())).strip()


def _round_coord(value: Any, places: int = 4) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return round(f, places)


def _hash(value: str) -> str:
    """Return a short stable hash for the printable dedupe key."""
    h = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return h[:24]


# ---------------------------------------------------------------------------
# The single public entry point
# ---------------------------------------------------------------------------
def compute_dedupe_key(extracted: Dict[str, Any]) -> Tuple[str, str]:
    """Return ``(dedupe_key, source)`` for an extracted property dict.

    ``source`` is the signal that won: ``"listing_id"``, ``"address"``,
    ``"geo"`` or ``"fallback"``. Useful for diagnostics.
    """
    if not isinstance(extracted, dict):
        extracted = {}

    listing_url = extracted.get("listing_url") or extracted.get("url") or extracted.get("source_url")
    listing_id = parse_idealista_property_id(listing_url)
    if listing_id:
        return _hash(f"{DEDUPE_KEY_VERSION}|listing_id|idealista|{listing_id}"), "listing_id"

    address = normalize_address(extracted.get("address"))
    city = normalize_city(extracted.get("city") or "Barcelona")
    if address and city:
        return _hash(f"{DEDUPE_KEY_VERSION}|address|{city}|{address}"), "address"

    lat = _round_coord(extracted.get("latitude") or extracted.get("lat"))
    lng = _round_coord(extracted.get("longitude") or extracted.get("lng"))
    if lat is not None and lng is not None:
        return _hash(f"{DEDUPE_KEY_VERSION}|geo|{lat}|{lng}"), "geo"

    # Last-resort fallback — never duplicate identical raw URLs.
    if listing_url:
        return _hash(f"{DEDUPE_KEY_VERSION}|url|{listing_url}"), "fallback"

    # No signal at all — generate a non-colliding random-ish key from the
    # whole extracted payload so the row still inserts but doesn't merge
    # with anything else.
    blob = repr(sorted(extracted.items()))[:512]
    return _hash(f"{DEDUPE_KEY_VERSION}|none|{blob}"), "fallback"


# ---------------------------------------------------------------------------
# Lookup helpers (DB-aware)
# ---------------------------------------------------------------------------
def find_existing_active_property(supabase, dedupe_key: Optional[str], listing_url: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return the active (non-deleted) property that matches a dedupe key or url.

    Used by the scan pipeline to UPSERT instead of INSERT. Tolerant of all
    failures — returns None on error so the caller falls back to insert.
    """
    if not supabase:
        return None
    try:
        if dedupe_key:
            res = (
                supabase.table("properties")
                .select("*")
                .eq("dedupe_key", dedupe_key)
                .is_("deleted_at", "null")
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0]
    except Exception:
        pass
    try:
        if listing_url:
            res = (
                supabase.table("properties")
                .select("*")
                .eq("listing_url", listing_url)
                .is_("deleted_at", "null")
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0]
    except Exception:
        pass
    return None
