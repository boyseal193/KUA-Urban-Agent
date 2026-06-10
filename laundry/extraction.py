"""Heuristic extraction of property facts from raw listing text / HTML.

Optional OpenAI augmentation if ``openai`` library + ``OPENAI_API_KEY`` is
available. Falls back to pure regex always — production never blocks on the LLM.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

log = logging.getLogger("kua.laundry.extraction")

_M2_RE = re.compile(r"(\d{2,4}(?:[.,]\d+)?)\s*m[²2]?", re.IGNORECASE)
_PRICE_RE = re.compile(
    r"(?:precio|price|asking|venta)\s*[:\-]?\s*€?\s*([\d\.\,]+)",
    re.IGNORECASE,
)
_RENT_RE = re.compile(
    r"(?:alquiler|rent|renta|mensual)\s*[:\-]?\s*€?\s*([\d\.\,]+)\s*(?:/\s*mes|/month|€/mes)?",
    re.IGNORECASE,
)
_CEIL_RE = re.compile(r"(?:altura|ceiling|techo)\s*[:\-]?\s*([\d\.,]+)\s*m", re.IGNORECASE)
_IDEALISTA_TITLE_RE = re.compile(
    r"(?:Local|Local comercial|Oficina|Nave)[^,\n]{0,120}(?:Barcelona|Hospitalet)[^,\n]{0,80}",
    re.IGNORECASE,
)
_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

_HOOD_HINTS = (
    "Raval", "Sant Antoni", "Poble Sec", "Clot", "Hospitalet", "L'Hospitalet",
    "Sants", "Gracia", "Gràcia", "Eixample", "Barri Gòtic", "Gothic Quarter",
    "Poblenou", "Les Corts", "Sarrià", "Sant Gervasi", "Nou Barris",
)


def _num(s) -> Optional[float]:
    if not s:
        return None
    s = str(s)
    if s.count(",") and s.count("."):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in extra.items():
        if v in (None, "", []):
            continue
        if out.get(k) in (None, "", []):
            out[k] = v
    return out


def _extract_jsonld(html: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not html:
        return out
    for match in _JSONLD_RE.finditer(html):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("name") and not out.get("title"):
                out["title"] = str(node["name"]).strip()
            if node.get("description") and not out.get("description"):
                out["description"] = str(node["description"]).strip()[:4000]
            addr = node.get("address")
            if isinstance(addr, dict):
                if addr.get("streetAddress") and not out.get("address"):
                    out["address"] = str(addr["streetAddress"]).strip()
                if addr.get("addressLocality") and not out.get("city"):
                    out["city"] = str(addr["addressLocality"]).strip()
                if addr.get("addressRegion") and not out.get("city"):
                    out["city"] = str(addr["addressRegion"]).strip()
            offers = node.get("offers")
            if isinstance(offers, dict):
                price = offers.get("price")
                if price is not None and not out.get("asking_price"):
                    out["asking_price"] = _num(price)
            if node.get("floorSize") and not out.get("floor_area_m2"):
                fs = node["floorSize"]
                if isinstance(fs, dict) and fs.get("value"):
                    out["floor_area_m2"] = _num(fs["value"])
    return out


def _extract_from_html(html: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not html:
        return out

    out = _merge(out, _extract_jsonld(html))

    og_title = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if og_title and not out.get("title"):
        out["title"] = og_title.group(1).strip()

    meta_desc = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if meta_desc and not out.get("description"):
        out["description"] = meta_desc.group(1).strip()[:4000]

    h1 = re.search(r"<h1[^>]*>([^<]{4,200})</h1>", html, re.IGNORECASE)
    if h1 and not out.get("title"):
        out["title"] = re.sub(r"\s+", " ", h1.group(1)).strip()

    idealista_addr = re.search(
        r'itemprop=["\']streetAddress["\'][^>]*>([^<]{4,120})<',
        html,
        re.IGNORECASE,
    )
    if idealista_addr and not out.get("address"):
        out["address"] = idealista_addr.group(1).strip()

    idealista_city = re.search(
        r'itemprop=["\']addressLocality["\'][^>]*>([^<]{2,80})<',
        html,
        re.IGNORECASE,
    )
    if idealista_city and not out.get("city"):
        out["city"] = idealista_city.group(1).strip()

    return out


def _heuristic_extract(text: str) -> Dict[str, Any]:
    t = text or ""
    lower = t.lower()

    out: Dict[str, Any] = {
        "title": None,
        "description": None,
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
        "ground_floor": None,
        "floor_level": None,
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
    if m:
        out["floor_area_m2"] = _num(m.group(1))
    m = _PRICE_RE.search(t)
    if m:
        out["asking_price"] = _num(m.group(1))
    m = _RENT_RE.search(t)
    if m:
        out["asking_rent_month"] = _num(m.group(1))
    m = _CEIL_RE.search(t)
    if m:
        out["ceiling_height"] = _num(m.group(1))

    if any(k in lower for k in ("alquiler", "rent", "/mes", "/month", "€/mes")):
        out["acquisition_type"] = "rent"
    if any(k in lower for k in ("venta", "for sale", "se vende")):
        out["acquisition_type"] = "buy"

    if any(k in lower for k in ("local comercial", "retail", "tienda")):
        out["property_type"] = "retail"
    if any(k in lower for k in ("lavandería", "laundromat", "laundry")):
        out["property_type"] = "existing_laundromat"

    if "esquina" in lower or "corner" in lower:
        out["corner_unit"] = True
    if "carga" in lower or "loading" in lower:
        out["loading_access"] = True
    if "sin gas" in lower or "no gas" in lower:
        out["gas_available"] = False
    if "trifásic" in lower or "three phase" in lower:
        out["three_phase_power"] = True
    if "ruido" in lower and "limit" in lower:
        out["noise_restriction"] = True
    if "cambio de uso" in lower or "change of use" in lower:
        out["requires_change_of_use"] = True

    if any(
        k in lower
        for k in (
            "planta baja",
            "ground floor",
            "bajo comercial",
            "local en planta baja",
            "planta 0",
            "piso 0",
        )
    ):
        out["ground_floor"] = True
        out["floor_level"] = "ground"
    elif re.search(r"\b(?:planta|piso|floor)\s*(?:[2-9]|[1-9]\d)", lower):
        out["ground_floor"] = False
        out["floor_level"] = "upper"
    elif any(
        k in lower
        for k in (
            "primera planta",
            "1ª planta",
            "1a planta",
            "second floor",
            "upper floor",
            "planta 1",
            "piso 1",
            "not ground floor",
            "sin planta baja",
        )
    ):
        out["ground_floor"] = False
        out["floor_level"] = "upper"
    elif re.search(r"\b(?:planta|piso)\s*baja\b", lower):
        out["ground_floor"] = True
        out["floor_level"] = "ground"

    addr_match = re.search(
        r"(?:dirección|address|calle|c/|carrer|ubicación)\s*[:\-]?\s*([^\n,]{6,120})",
        t,
        re.IGNORECASE,
    )
    if addr_match:
        out["address"] = addr_match.group(1).strip()

    title_match = _IDEALISTA_TITLE_RE.search(t)
    if title_match and not out.get("title"):
        out["title"] = title_match.group(0).strip()

    for hood in _HOOD_HINTS:
        if hood.lower() in lower:
            out["neighbourhood"] = hood
            break

    return out


def _maybe_llm_augment(text: str, base: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort OpenAI augmentation. Silently returns base on any failure."""
    if not os.environ.get("OPENAI_API_KEY"):
        return base
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI()
        prompt = (
            "Extract laundromat-relevant facts from this listing as compact JSON. "
            "Fields: title, description, address, neighbourhood, city, "
            "property_type (existing_laundromat|empty_commercial|retail|mixed_use), "
            "acquisition_type (buy|rent), floor_area_m2, asking_price, asking_rent_month, "
            "ceiling_height, washer_count, dryer_count, ground_floor, corner_unit, "
            "loading_access, water_available, gas_available, drainage_available, "
            "three_phase_power, noise_restriction, requires_change_of_use. "
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
            return _merge(base, payload)
    except Exception as exc:  # pragma: no cover
        log.warning("LLM augmentation failed: %s", exc)
    return base


def extract_from_text(text: str, *, use_llm: bool = True) -> Dict[str, Any]:
    base = _heuristic_extract(text or "")
    if use_llm:
        base = _maybe_llm_augment(text or "", base)
    return base


def extract_listing(
    text: str,
    *,
    html: Optional[str] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """Extract listing fields from scraped text and optional raw HTML."""
    base = _heuristic_extract(text or "")
    if html:
        base = _merge(base, _extract_from_html(html))
    if use_llm:
        base = _maybe_llm_augment(text or "", base)
    return base


def has_usable_fields(extracted: Dict[str, Any]) -> bool:
    """True when we extracted enough to run underwriting (not a bare URL)."""
    if not isinstance(extracted, dict):
        return False
    return any(
        extracted.get(k) not in (None, "", 0)
        for k in (
            "address",
            "neighbourhood",
            "title",
            "floor_area_m2",
            "asking_price",
            "asking_rent_month",
            "description",
        )
    )
