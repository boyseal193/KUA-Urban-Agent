"""
LLM-backed (or rule-based fallback) extraction of laundromat listings.

The async extractor will use whichever ``LLM_PROVIDER`` is configured in
``app.ai.providers.base`` (OpenAI / Claude / Local). When no provider is
reachable the heuristic regex fallback returns a best-effort dictionary so the
pipeline never blocks on AI availability.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Optional

import structlog

log = structlog.get_logger(__name__)


_NUM = r"(\d[\d.,]*)"
_AREA_PATTERNS = [re.compile(r"(\d[\d.,]*)\s*m(?:²|2)\b", re.IGNORECASE)]
_PRICE_PATTERNS = [
    re.compile(r"€\s*" + _NUM, re.IGNORECASE),
    re.compile(_NUM + r"\s*(?:€|eur|EUR)", re.IGNORECASE),
]
_RENT_PATTERNS = [
    re.compile(r"(?:rent|renta|alquiler)[^€\d]{0,12}€?\s*" + _NUM, re.IGNORECASE),
    re.compile(_NUM + r"\s*€?\s*/\s*(?:month|mes|mo)", re.IGNORECASE),
]
_WASHER_PATTERN = re.compile(r"(\d+)\s*(?:washer|washers|lavadora|lavadoras)", re.IGNORECASE)
_DRYER_PATTERN = re.compile(r"(\d+)\s*(?:dryer|dryers|secadora|secadoras)", re.IGNORECASE)
_CEILING_PATTERN = re.compile(r"(?:ceiling|altura)[^0-9]{0,10}([\d.,]+)\s*m\b", re.IGNORECASE)


EXTRACTION_SYSTEM_PROMPT = (
    "You are a precise commercial real estate analyst extracting structured data "
    "from a property listing for evaluating its suitability as a self-service "
    "laundromat (existing or convertible). Never invent numbers. Use null when "
    "the listing does not state the value. Return STRICT JSON only — no prose."
)

EXTRACTION_INSTRUCTIONS = """Return a JSON object with these keys:

{
  "address": string | null,
  "city": string | null,
  "neighbourhood": string | null,
  "floor_area_m2": number | null,
  "ceiling_height": number | null,
  "asking_price": number | null,
  "asking_rent_month": number | null,
  "property_type": "existing_laundromat" | "empty_commercial" | "retail" | "mixed_use" | "industrial" | null,
  "acquisition_type": "buy" | "rent" | null,
  "ground_floor": boolean | null,
  "loading_access": boolean | null,
  "corner_unit": boolean | null,
  "water_available": boolean | null,
  "gas_available": boolean | null,
  "drainage_available": boolean | null,
  "three_phase_power": boolean | null,
  "washer_count": integer | null,
  "dryer_count": integer | null,
  "requires_change_of_use": boolean | null,
  "noise_restriction": boolean | null,
  "flood_risk_flag": boolean | null,
  "structural_issue_flag": boolean | null,
  "description": string | null
}

Only include the JSON object. Do not include markdown fences.
"""


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", False):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace(".", "", str(value).count(".") - 1))
    except (TypeError, ValueError):
        return None


def _heuristic_extract(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "floor_area_m2": None,
        "asking_price": None,
        "asking_rent_month": None,
        "washer_count": None,
        "dryer_count": None,
        "ceiling_height": None,
        "ground_floor": None,
        "description": text[:1500] if text else None,
    }
    if not text:
        return out

    for pattern in _AREA_PATTERNS:
        m = pattern.search(text)
        if m:
            out["floor_area_m2"] = _to_float(m.group(1).replace(".", "").replace(",", "."))
            break

    for pattern in _PRICE_PATTERNS:
        m = pattern.search(text)
        if m:
            n = _to_float(m.group(1).replace(".", "").replace(",", "."))
            if n is not None and n > 1000:
                out["asking_price"] = n
                break

    for pattern in _RENT_PATTERNS:
        m = pattern.search(text)
        if m:
            n = _to_float(m.group(1).replace(".", "").replace(",", "."))
            if n is not None and 100 <= n <= 50_000:
                out["asking_rent_month"] = n
                break

    if (m := _WASHER_PATTERN.search(text)):
        out["washer_count"] = int(m.group(1))
    if (m := _DRYER_PATTERN.search(text)):
        out["dryer_count"] = int(m.group(1))
    if (m := _CEILING_PATTERN.search(text)):
        out["ceiling_height"] = _to_float(m.group(1).replace(",", "."))

    lowered = text.lower()
    if any(k in lowered for k in ["planta baja", "ground floor", "street level"]):
        out["ground_floor"] = True
    if any(k in lowered for k in ["esquina", "corner unit"]):
        out["corner_unit"] = True
    if "lavandería" in lowered or "laundromat" in lowered or "self-service" in lowered:
        out["property_type"] = "existing_laundromat"
    return out


async def extract_listing(text: str) -> Dict[str, Any]:
    """
    Run AI extraction with the configured provider; fall back to regex on any error.

    The returned dictionary is *not* validated — that happens in
    :mod:`app.laundry.services.normalization`.
    """
    if not text:
        return {}

    heuristic = _heuristic_extract(text)

    try:
        from app.ai.providers.base import get_provider  # lazy — avoids LLM dep chain at import time

        provider = get_provider()
        prompt = EXTRACTION_INSTRUCTIONS + "\n\n--- LISTING TEXT ---\n" + text[:8000]
        raw = await provider.complete(EXTRACTION_SYSTEM_PROMPT, prompt, max_tokens=1200)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).rsplit("```", 1)[0].strip()
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("provider returned non-object payload")
        merged = {**heuristic, **{k: v for k, v in data.items() if v not in (None, "")}}
        return merged
    except Exception as e:
        log.warning("laundry.extraction_fallback", error=str(e))
        return heuristic
