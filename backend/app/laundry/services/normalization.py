"""Normalisation + validation for raw laundromat listing dictionaries."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Optional, Tuple


_VALID_PROPERTY_TYPES = {
    "existing_laundromat",
    "empty_commercial",
    "retail",
    "mixed_use",
    "industrial",
}

_VALID_ACQUISITION_TYPES = {"buy", "rent"}


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = (
            value.strip()
            .replace(",", ".")
            .replace("€", "")
            .replace("eur", "")
            .replace("m²", "")
            .replace("m2", "")
        )
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _safe_int(value: Any) -> Optional[int]:
    f = _safe_float(value)
    if f is None:
        return None
    return int(round(f))


def _norm_str(value: Any, lower: bool = False) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s.lower() if lower else s


def clean_listing(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise an extracted listing dict into a stable, JSON-safe shape."""
    if not data:
        return {}

    out: Dict[str, Any] = dict(data)

    out["address"] = _norm_str(out.get("address"))
    out["city"] = _norm_str(out.get("city"))
    out["neighbourhood"] = _norm_str(out.get("neighbourhood"))

    out["floor_area_m2"] = _safe_float(out.get("floor_area_m2") or out.get("gba_m2") or out.get("size_m2"))
    out["ceiling_height"] = _safe_float(out.get("ceiling_height"))
    out["asking_price"] = _safe_float(out.get("asking_price"))
    out["asking_rent_month"] = _safe_float(out.get("asking_rent_month") or out.get("monthly_rent"))
    out["washer_count"] = _safe_int(out.get("washer_count"))
    out["dryer_count"] = _safe_int(out.get("dryer_count"))

    property_type = _norm_str(out.get("property_type"), lower=True)
    if property_type not in _VALID_PROPERTY_TYPES:
        property_type = None
    out["property_type"] = property_type

    acquisition_type = _norm_str(out.get("acquisition_type"), lower=True)
    if acquisition_type not in _VALID_ACQUISITION_TYPES:
        if out["asking_rent_month"] and not out["asking_price"]:
            acquisition_type = "rent"
        elif out["asking_price"]:
            acquisition_type = "buy"
        else:
            acquisition_type = None
    out["acquisition_type"] = acquisition_type

    for bool_field in (
        "ground_floor",
        "loading_access",
        "corner_unit",
        "water_available",
        "gas_available",
        "drainage_available",
        "three_phase_power",
        "requires_change_of_use",
        "noise_restriction",
        "flood_risk_flag",
        "structural_issue_flag",
    ):
        v = out.get(bool_field)
        if v is None:
            continue
        out[bool_field] = bool(v) if not isinstance(v, str) else v.strip().lower() in ("true", "yes", "1", "si", "sí")

    if out.get("description"):
        out["description"] = str(out["description"]).strip()[:4000]

    return out


def is_valid_listing(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not data:
        return False, "No listing data extracted"
    if not data.get("floor_area_m2") or (data.get("floor_area_m2") or 0) <= 0:
        return False, "Missing or invalid floor area (m²)"
    if not (data.get("asking_price") or data.get("asking_rent_month")):
        return False, "Missing both asking price and monthly rent"
    if data.get("acquisition_type") not in _VALID_ACQUISITION_TYPES:
        return False, "Cannot infer acquisition type (buy/rent)"
    return True, None


def dedupe_key(data: Dict[str, Any]) -> str:
    """Stable hash used for soft-dedupe across re-scans of the same property."""
    parts = [
        (data.get("listing_url") or "").strip().lower(),
        (data.get("address") or "").strip().lower(),
        str(data.get("city") or "").lower(),
        f"{round((data.get('floor_area_m2') or 0), 1)}",
        f"{round((data.get('asking_price') or 0), 0)}",
        f"{round((data.get('asking_rent_month') or 0), 0)}",
    ]
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def assign_deal_status(score_result: Dict[str, Any]) -> str:
    """Authoritative deal_status from a scoring result (already computed)."""
    return score_result.get("deal_status", "manual_review")
