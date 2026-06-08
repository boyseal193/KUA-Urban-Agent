"""
Deterministic SWOT + red-flag + due-diligence checklist generator.

The output is rendered straight into the IC memo and is also exposed as JSON
on the deal detail page so operators can tick items off the verification list.
"""
from __future__ import annotations

from typing import Any, Dict, List


def build_due_diligence(
    *,
    property_data: Dict[str, Any],
    economics: Dict[str, Any],
    score_result: Dict[str, Any],
    location: Dict[str, Any],
) -> Dict[str, Any]:
    strengths: List[str] = []
    weaknesses: List[str] = []
    opportunities: List[str] = []
    threats: List[str] = []
    red_flags: List[str] = []
    required_verifications: List[str] = []

    sub = score_result.get("auto_scores", {}).get("sub_components", {})

    if (economics.get("payback_years") or 99) <= 5:
        strengths.append(f"Fast payback ({economics.get('payback_years')} years)")
    if (economics.get("operating_margin") or 0) >= 0.30:
        strengths.append(f"Healthy EBITDA margin ({round(economics['operating_margin']*100, 1)}%)")
    if score_result.get("auto_scores", {}).get("competition_score", 0) >= 70:
        strengths.append("Low competition density within the catchment")
    if sub.get("visibility", 0) >= 75:
        strengths.append("Strong street visibility")
    if location.get("corner_unit"):
        strengths.append("Corner unit footprint")
    if sub.get("demand_signal", 0) >= 70:
        strengths.append("High residential / student demand signal")

    if (economics.get("payback_years") or 0) >= 9:
        weaknesses.append("Long projected payback (>9 years)")
    if (economics.get("operating_margin") or 0) < 0.15:
        weaknesses.append("Tight operating margin")
    if score_result.get("auto_scores", {}).get("competition_score", 0) < 40:
        weaknesses.append("Saturated competitor field within 500 m")
    if (economics.get("floor_area_m2") or 0) < 35:
        weaknesses.append("Sub-optimal floor area for full machine line-up")
    if not property_data.get("ground_floor", True):
        weaknesses.append("Upper-floor / basement access risk")
    if not property_data.get("three_phase_power"):
        weaknesses.append("Three-phase electrical upgrade likely required")

    if (location.get("growth_potential_0_100") or 0) >= 70:
        opportunities.append("Neighbourhood expansion trajectory supports rent growth")
    if economics.get("acquisition_type") == "rent" and (economics.get("payback_years") or 99) <= 4:
        opportunities.append("Lease structure with rapid payback — scalable to franchise model")
    if property_data.get("property_type") == "existing_laundromat":
        opportunities.append("Operating cashflow from day one — runway risk minimised")
    if (location.get("students_within_1km") or 0) >= 1500:
        opportunities.append("University catchment supports premium pricing on dryers")
    if economics.get("ancillary_revenue_eur", 0) >= 5000:
        opportunities.append("Ancillary vending + detergent sales support incremental margin")

    if (location.get("nearby_laundromats_within_500m") or 0) >= 5:
        threats.append("Direct competitor cluster within 500 m")
    if property_data.get("requires_change_of_use"):
        threats.append("Change-of-use permit required — timeline + cost risk")
    if property_data.get("noise_restriction"):
        threats.append("Noise restriction may limit nighttime opening hours")
    if property_data.get("flood_risk_flag"):
        threats.append("Flood-zone designation — insurance and capex impact")
    if (economics.get("rent_cost_eur") or 0) > (economics.get("expected_revenue_eur") or 1) * 0.18:
        threats.append("Rent burden exceeds 18% of revenue — squeezes margin")

    # Red flags ------------------------------------------------------------
    if property_data.get("structural_issue_flag"):
        red_flags.append("Listing mentions structural / damp / facade issue — engineer survey required")
    if not property_data.get("water_available", True):
        red_flags.append("No existing water supply — heavy plumbing capex risk")
    if not property_data.get("drainage_available", True):
        red_flags.append("No drainage infrastructure — major civil works probable")
    if not property_data.get("gas_available", True):
        red_flags.append("No gas connection — dryers must run on electric (higher opex)")

    # Required verifications ----------------------------------------------
    required_verifications.extend(
        [
            "Confirm change-of-use permit pathway with local authority",
            "Obtain 12 months of utility bills (water, electricity, gas)",
            "Validate three-phase electricity supply & available capacity",
            "Walk catchment at peak and off-peak hours; observe competitor footfall",
            "Verify drainage and grease-trap suitability with municipal records",
            "Confirm signage and façade permits available for laundromat use",
            "Obtain landlord consent letter (rent deals) covering 24/7 operating hours",
            "Commission noise impact assessment if residential units sit above",
            "Cross-check washer/dryer count against legal max-load fire regulations",
        ]
    )
    if property_data.get("property_type") == "existing_laundromat":
        required_verifications.extend(
            [
                "Audit machine maintenance logs and remaining useful life",
                "Reconcile reported revenue with payment processor statements",
                "Verify continuity of staff contracts / TUPE obligations",
            ]
        )

    confidence = score_result.get("confidence", {})
    risks = list(score_result.get("drivers", {}).get("risk", []))

    next_steps = []
    if score_result.get("deal_status") == "approved_candidate":
        next_steps = [
            "Issue NDA + LOI request to broker / seller",
            "Trigger site visit within 7 days",
            "Commission utility infrastructure audit",
            "Draft term sheet aligned with model assumptions",
        ]
    elif score_result.get("deal_status") == "manual_review":
        next_steps = [
            "Operator review — verify weakest sub-score before progressing",
            "Request floorplan + utility schematics from broker",
            "Confirm competitor footfall via on-the-ground inspection",
            "Re-run model with verified utility unit prices",
        ]
    else:
        next_steps = [
            "Log rejection rationale; revisit if asking price drops >15%",
            "Re-add to monitoring queue every 30 days for repricing",
        ]

    return {
        "strengths": strengths or ["No standout strengths detected"],
        "weaknesses": weaknesses or ["No structural weaknesses detected"],
        "opportunities": opportunities or ["Standard urban laundromat economics"],
        "threats": threats or ["No material threats detected"],
        "red_flags": red_flags,
        "risks": risks,
        "due_diligence_checklist": required_verifications,
        "required_verification": required_verifications,
        "next_steps": next_steps,
        "confidence": confidence,
    }
