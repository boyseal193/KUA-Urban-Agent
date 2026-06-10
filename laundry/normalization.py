"""Listing normalization + dedupe key generation."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Optional


_WHITESPACE_RE = re.compile(r"\s+")


def _clean_str(v) -> Optional[str]:
    if v is None: return None
    s = str(v).strip()
    if not s: return None
    return _WHITESPACE_RE.sub(" ", s)


def _safe_float(v) -> Optional[float]:
    if v is None or isinstance(v, bool): return None
    if isinstance(v, (int, float)): return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", ".").replace("€", "").replace("eur", "").replace("EUR", "")
        s = re.sub(r"[^\d\.\-]", "", s)
        try: return float(s) if s else None
        except ValueError: return None
    return None


def _safe_int(v) -> Optional[int]:
    f = _safe_float(v)
    return int(round(f)) if f is not None else None


def normalize_extracted(extracted: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(extracted, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in extracted.items():
        if isinstance(v, str):
            out[k] = _clean_str(v)
        else:
            out[k] = v
    out["floor_area_m2"] = _safe_float(out.get("floor_area_m2") or out.get("gba_m2") or out.get("size_m2"))
    out["asking_price"] = _safe_float(out.get("asking_price"))
    out["asking_rent_month"] = _safe_float(out.get("asking_rent_month"))
    out["ceiling_height"] = _safe_float(out.get("ceiling_height"))
    out["washer_count"] = _safe_int(out.get("washer_count"))
    out["dryer_count"] = _safe_int(out.get("dryer_count"))
    out["acquisition_type"] = (out.get("acquisition_type") or "").lower() or None
    if out.get("acquisition_type") not in ("buy", "rent", None):
        out["acquisition_type"] = None
    out["property_type"] = (out.get("property_type") or "").lower() or None
    if not out.get("city"): out["city"] = "Barcelona"
    if "ground_floor" in out and out.get("ground_floor") is not None:
        out["ground_floor"] = bool(out["ground_floor"])
    return out


def ground_floor_value(extracted: Optional[Dict[str, Any]]) -> Optional[bool]:
    """Tri-state ground floor: True, False, or None (unknown)."""
    if not isinstance(extracted, dict):
        return None
    if "ground_floor" not in extracted:
        return None
    val = extracted.get("ground_floor")
    if val is None:
        return None
    return bool(val)


def ground_floor_status(extracted: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Human-readable ground-floor status for UI and exports."""
    val = ground_floor_value(extracted)
    if val is True:
        return {
            "ground_floor": True,
            "label": "Ground floor",
            "short_label": "GF",
            "tone": "positive",
            "verification": "confirmed",
        }
    if val is False:
        return {
            "ground_floor": False,
            "label": "Not ground floor",
            "short_label": "Upper",
            "tone": "warning",
            "verification": "confirmed",
        }
    return {
        "ground_floor": None,
        "label": "Floor unknown — verify on site",
        "short_label": "Verify",
        "tone": "caution",
        "verification": "required",
    }


def laundromat_access_impossible(extracted: Optional[Dict[str, Any]]) -> bool:
    """True only when upper-floor access makes a laundromat physically impractical."""
    if not isinstance(extracted, dict):
        return False
    if ground_floor_value(extracted) is not False:
        return False
    if extracted.get("loading_access"):
        return False
    floor_area = _safe_float(extracted.get("floor_area_m2")) or 0.0
    if floor_area >= 120:
        return True
    if extracted.get("requires_freight_elevator") is False:
        return True
    return False


def make_dedupe_key(*, listing_url: Optional[str], address: Optional[str],
                     city: Optional[str], floor_area_m2: Optional[float]) -> str:
    if listing_url:
        norm = listing_url.lower().split("?")[0].rstrip("/")
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()
    parts = [
        (city or "").strip().lower(),
        (address or "").strip().lower(),
        f"{round(floor_area_m2 or 0, 1)}",
    ]
    raw = "|".join(p for p in parts if p)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else hashlib.sha256(b"unknown").hexdigest()
