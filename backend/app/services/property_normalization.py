"""Normalize listing / extracted payloads (ported from legacy `main.py`)."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip().lower()
        value = value.replace(",", ".")
        value = value.replace("m²", "")
        value = value.replace("m2", "")
        value = value.replace("meters", "")
        value = value.replace("metres", "")
        value = value.replace("€", "")
        value = value.replace("eur", "")
        value = value.strip()
        nums = re.findall(r"\d+(?:\.\d+)?", value)
        if len(nums) >= 2:
            nums_f = [float(x) for x in nums[:2]]
            return round(sum(nums_f) / len(nums_f), 2)
        if len(nums) == 1:
            return float(nums[0])
    return default


def clean_property_data(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data:
        return {}
    cleaned = dict(data)
    cleaned["gba_m2"] = safe_float(cleaned.get("gba_m2"))
    cleaned["asking_price"] = safe_float(cleaned.get("asking_price"))
    cleaned["asking_rent_month"] = safe_float(cleaned.get("asking_rent_month"))
    cleaned["rent_per_m2"] = safe_float(cleaned.get("rent_per_m2"))
    cleaned["ceiling_height"] = safe_float(cleaned.get("ceiling_height"))
    cleaned["price_per_m2_nra"] = safe_float(cleaned.get("price_per_m2_nra"))
    cleaned["nra_efficiency"] = safe_float(cleaned.get("nra_efficiency"))
    if cleaned.get("city") is None:
        cleaned["city"] = "Barcelona"
    if cleaned.get("price_per_m2_nra") is None:
        cleaned["price_per_m2_nra"] = 15
    if cleaned.get("nra_efficiency") is None:
        cleaned["nra_efficiency"] = 0.75
    if cleaned.get("loading_access") is None:
        cleaned["loading_access"] = False
    return cleaned


def is_valid_property_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not data:
        return False, "No extracted property data"
    if data.get("gba_m2") is None or data.get("gba_m2") <= 0:
        return False, "Missing or invalid GBA"
    if data.get("asking_price") is None and data.get("asking_rent_month") is None:
        return False, "Missing both asking price and asking rent"
    return True, None


def assign_deal_status(score: Dict[str, Any]) -> str:
    score_value = score.get("score", 0)
    verdict = score.get("verdict")
    deal_killer = score.get("deal_killer")
    if deal_killer:
        return "rejected"
    if verdict == "YES" and score_value >= 80:
        return "approved_candidate"
    if score_value >= 60:
        return "manual_review"
    return "rejected"


def generate_rejection_note(property_data: dict, economics: dict, score: dict) -> str:
    return f"""
# REJECTION SUMMARY

Property: {property_data.get("address")}, {property_data.get("city")}
Verdict: {score.get("verdict")}
Score: {score.get("score")}/100
Classification: {score.get("classification")}
Deal killer: {score.get("deal_killer") or "Score below investment threshold"}

Key metrics:
- GBA: {property_data.get("gba_m2")} m²
- Asking price: €{property_data.get("asking_price")}
- EBITDA: €{economics.get("ebitda")}
- EBITDA yield: {economics.get("ebitda_yield")}
- True EBITDA yield: {economics.get("true_ebitda_yield")}
- Payback years: {economics.get("payback_years")}
- True payback years: {economics.get("true_payback_years")}

Reason:
This deal was rejected automatically because it does not meet the minimum TruTrastero investment threshold. It remains saved in the rejected history for manual review.
""".strip()
