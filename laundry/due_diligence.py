"""Heuristic SWOT, red flags, and due-diligence checklist for laundromat deals."""
from __future__ import annotations

from typing import Any, Dict, List

from laundry.normalization import ground_floor_value


def _push(arr: List[str], cond: bool, text: str) -> None:
    if cond and text not in arr:
        arr.append(text)


def build_due_diligence(*, extracted: Dict[str, Any], economics: Dict[str, Any],
                         scoring: Dict[str, Any], location: Dict[str, Any]) -> Dict[str, Any]:
    strengths: List[str] = []
    weaknesses: List[str] = []
    opportunities: List[str] = []
    threats: List[str] = []
    risks: List[str] = []
    checklist: List[str] = []
    red_flags: List[str] = []

    score = scoring.get("score", 0)
    deal_status = scoring.get("deal_status", "rejected")
    drivers = scoring.get("drivers", {}) or {}
    confidence = scoring.get("confidence", {}) or {}

    _push(strengths, score >= 75, "Composite score above approval threshold (>=75)")
    _push(strengths, (economics.get("payback_years") or 99) <= 5, "Payback under 5 years")
    _push(strengths, (economics.get("operating_margin") or 0) >= 0.30, "Operating margin above 30%")
    _push(strengths, scoring.get("preferred_market", {}).get("matched"),
          f"Located in operator target market: {scoring.get('preferred_market', {}).get('matched')}")
    _push(strengths, (economics.get("secondary_revenue_eur") or 0) > 6_000,
          "Material secondary revenue (lockers / vending / drop-off)")
    gf = ground_floor_value(extracted)
    _push(strengths, gf is True and bool(extracted.get("loading_access")),
          "Ground floor with loading access")
    _push(strengths, gf is True, "Ground floor — strong laundromat fit")

    _push(weaknesses, (economics.get("payback_years") or 99) > 8, "Long payback period (>8y)")
    _push(weaknesses, (economics.get("operating_margin") or 0) < 0.20, "Thin operating margin (<20%)")
    _push(weaknesses, gf is False, "Not ground floor — major access warning (manual review)")
    _push(weaknesses, gf is None, "Floor level unknown — on-site verification required")
    _push(weaknesses, not extracted.get("loading_access"), "No dedicated loading access")
    _push(weaknesses, confidence.get("band") == "low", "Low data confidence — many key fields unknown")

    _push(opportunities, deal_status != "rejected", "Add Amazon / InPost locker for steady ancillary income")
    _push(opportunities, deal_status != "rejected", "Test drop-off / wash-and-fold concierge service")
    _push(opportunities, int(location.get("hotels_within_500m") or 0) >= 3,
          "Hotel proximity — pitch B2B contracts (linen, towels)")
    _push(opportunities, int(location.get("students_within_1km") or 0) >= 600,
          "Student density — build subscription bundles")

    _push(threats, int(location.get("competitors_within_1km") or 0) >= 8,
          "Saturated competitive market (>=8 within 1km)")
    _push(threats, (location.get("night_safety_0_100") or 65) < 50,
          "Below-average night-time safety")
    _push(threats, bool(extracted.get("noise_restriction")), "Possible noise restriction risk")
    _push(threats, bool(extracted.get("requires_change_of_use")),
          "Change-of-use permit may be required")

    for d in drivers.get("risk", []) or []: _push(risks, True, d.replace("_", " "))
    for d in drivers.get("economics", []) or []:
        if d.startswith("ebitda_neg"): _push(risks, True, "EBITDA negative or unknown")

    checklist += [
        "Verify floor level on-site (ground floor strongly preferred for laundromats).",
        "Confirm planta baja / street-level access for machine delivery.",
        "Verify floor area on-site (laser measurement).",
        "Confirm 3-phase power availability and meter capacity.",
        "Check existing water supply diameter and pressure.",
        "Inspect drainage system + grease/sediment trap requirements.",
        "Validate gas connection or budget for electric-only dryer fleet.",
        "Pull census data for renter / income / household size ratios.",
        "Walk 1km radius and count active laundromats (incl. hotels / hostels).",
        "Confirm change-of-use / licensing path with local municipality.",
        "Negotiate lease length >= 7 years with renewal option.",
        "Identify InPost / Amazon locker programmes in the area.",
    ]

    if (economics.get("payback_years") or 99) > 12: _push(red_flags, True, "Payback >12y — capital impossible to recover safely")
    if (economics.get("operating_margin") or 0) < 0.10: _push(red_flags, True, "Margin under 10% — no buffer for shocks")
    if int(location.get("competitors_within_1km") or 0) >= 12: _push(red_flags, True, "Severely oversaturated market")
    if extracted.get("structural_issue_flag"): _push(red_flags, True, "Possible structural issue declared")
    if extracted.get("flood_risk_flag"): _push(red_flags, True, "Known flood risk")
    if gf is None: _push(red_flags, True, "Floor level unverified — confirm ground-floor access")
    if gf is False: _push(red_flags, True, "Not ground floor — laundromat access risk")

    return {
        "swot": {
            "strengths": strengths or ["No standout strengths"],
            "weaknesses": weaknesses or ["No critical weaknesses identified"],
            "opportunities": opportunities or ["Standard market opportunities apply"],
            "threats": threats or ["No material threats identified"],
        },
        "risks": risks or ["Standard operational risks for European laundromats"],
        "due_diligence_checklist": checklist,
        "red_flags": red_flags,
        "confidence_band": confidence.get("band", "medium"),
        "required_verification": [
            "Census + INE demographic confirmation",
            "On-site mechanical/electrical survey",
            "Independent valuation of asking price/rent",
            "Direct contact with at least 3 nearby competitors",
        ],
    }
