"""Heuristic extraction of property facts from raw listing text.

Optional OpenAI augmentation if ``openai`` library + ``OPENAI_API_KEY`` is
available. Falls back to pure regex always — production never blocks on the LLM.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

log = logging.getLogger("kua.laundry.extraction")

_M2_RE = re.compile(r"(\d{2,4}(?:[.,]\d+)?)\s*m[²2]?", re.IGNORECASE)
_PRICE_RE = re.compile(r"(?:precio|price|asking)\s*[:\-]?\s*€?\s*([\d\.\,]+)", re.IGNORECASE)
_RENT_RE = re.compile(r"(?:alquiler|rent|renta)\s*[:\-]?\s*€?\s*([\d\.\,]+)\s*(?:/\s*mes|/month)?", re.IGNORECASE)
_CEIL_RE = re.compile(r"(?:altura|ceiling|techo)\s*[:\-]?\s*([\d\.,]+)\s*m", re.IGNORECASE)


def _num(s) -> Optional[float]:
    if not s: return None
    s = s.replace(".", "").replace(",", ".") if s.count(",") and s.count(".") else s.replace(",", ".")
    try: return float(s)
    except ValueError: return None


def _heuristic_extract(text: str) -> Dict[str, Any]:
    t = text or ""
    lower = t.lower()

    out: Dict[str, Any] = {
        "city": "Barcelona",
        "address": None,
        "neighbourhood": None,
        "property_type": None,
        "acquisition_type": None,
        "floor_area_m2": None,
        "asking_price": None,
        "asking_rent_month": None,
        "ceiling_height": None,
        "washer_count": None,
        "dryer_count": None,
        "ground_floor": True,
        "corner_unit": False,
        "loading_access": False,
        "water_available": True,
        "gas_available": True,
        "drainage_available": True,
        "three_phase_power": False,
        "noise_restriction": False,
        "requires_change_of_use": False,
        "flood_risk_flag": False,
        "structural_issue_flag": False,
    }

    m = _M2_RE.search(t)
    if m: out["floor_area_m2"] = _num(m.group(1))
    m = _PRICE_RE.search(t)
    if m: out["asking_price"] = _num(m.group(1))
    m = _RENT_RE.search(t)
    if m: out["asking_rent_month"] = _num(m.group(1))
    m = _CEIL_RE.search(t)
    if m: out["ceiling_height"] = _num(m.group(1))

    if any(k in lower for k in ("alquiler", "rent", "/mes", "/month")): out["acquisition_type"] = "rent"
    if any(k in lower for k in ("venta", "for sale", "se vende")): out["acquisition_type"] = "buy"

    if any(k in lower for k in ("local comercial", "retail", "tienda")): out["property_type"] = "retail"
    if any(k in lower for k in ("lavandería", "laundromat", "laundry")): out["property_type"] = "existing_laundromat"

    if "esquina" in lower or "corner" in lower: out["corner_unit"] = True
    if "carga" in lower or "loading" in lower: out["loading_access"] = True
    if "sin gas" in lower or "no gas" in lower: out["gas_available"] = False
    if "trifásic" in lower or "three phase" in lower: out["three_phase_power"] = True
    if "ruido" in lower and "limit" in lower: out["noise_restriction"] = True
    if "cambio de uso" in lower or "change of use" in lower: out["requires_change_of_use"] = True

    addr_match = re.search(r"(?:dirección|address|calle|c/|carrer)\s*[:\-]?\s*([^\n,]{6,80})", t, re.IGNORECASE)
    if addr_match: out["address"] = addr_match.group(1).strip()
    for hood in ("Raval", "Sant Antoni", "Poble Sec", "Clot", "Hospitalet", "L'Hospitalet",
                 "Sants", "Gracia", "Gràcia", "Eixample", "Barri Gòtic"):
        if hood.lower() in lower:
            out["neighbourhood"] = hood
            break
    return out


def _maybe_llm_augment(text: str, base: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort OpenAI augmentation. Silently returns base on any failure."""
    if not os.environ.get("OPENAI_API_KEY"):
        return base
    try:
        import json
        from openai import OpenAI  # type: ignore
        client = OpenAI()
        prompt = (
            "Extract laundromat-relevant facts from this listing as compact JSON. "
            "Fields: address, neighbourhood, city, property_type (existing_laundromat|empty_commercial|retail|mixed_use), "
            "acquisition_type (buy|rent), floor_area_m2, asking_price, asking_rent_month, ceiling_height, "
            "washer_count, dryer_count, ground_floor, corner_unit, loading_access, water_available, "
            "gas_available, drainage_available, three_phase_power, noise_restriction, requires_change_of_use. "
            "Return ONLY valid JSON. Listing:\n\n" + (text[:4000] if text else "")
        )
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        payload = json.loads(resp.choices[0].message.content)
        if isinstance(payload, dict):
            merged = {**base}
            for k, v in payload.items():
                if v not in (None, "", []): merged[k] = v
            return merged
    except Exception as exc:  # pragma: no cover
        log.warning("LLM augmentation failed: %s", exc)
    return base


def extract_from_text(text: str, *, use_llm: bool = True) -> Dict[str, Any]:
    base = _heuristic_extract(text or "")
    if use_llm:
        base = _maybe_llm_augment(text or "", base)
    return base
