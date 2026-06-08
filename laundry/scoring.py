"""
Laundromat opportunity scoring engine.

* ``>= 75``   approved_candidate (EXCELLENT)
* ``40-74``   manual_review (real-world good deals belong here)
* ``<  40``   rejected

Missing info never auto-rejects — it decays confidence. Low confidence
auto-promotes rejects to manual_review so an operator decides.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from laundry.assumptions import (
    BusinessProfile,
    LaundryAssumptions,
    default_assumptions,
    merge_overrides,
)


CRITICAL_LOCATION_FIELDS = [
    "population_density_per_km2",
    "household_income_eur",
    "walkability_score_0_100",
    "nearby_laundromats_within_500m",
    "competitors_within_1km",
    "apartment_density_pct",
    "students_within_1km",
    "street_visibility_0_100",
    "night_safety_0_100",
    "growth_potential_0_100",
]


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _safe_float(v, default=0.0):
    try:
        if v is None or isinstance(v, bool):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v, default=0):
    try:
        if v is None or isinstance(v, bool):
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Sub-scorers
# ---------------------------------------------------------------------------
def _score_population_density(v):
    if v <= 0: return 40.0
    if v < 6_000: return 35.0
    if v < 10_000: return 55.0
    if v < 16_000: return 82.0
    if v < 25_000: return 92.0
    if v < 35_000: return 78.0
    return 60.0


def _score_income(v):
    if v <= 0: return 45.0
    if v < 14_000: return 50.0
    if v < 22_000: return 80.0
    if v < 38_000: return 88.0
    if v < 55_000: return 70.0
    return 55.0


def _score_competition(nearby_500m, within_1km):
    base = 100.0
    base -= min(nearby_500m, 8) * 9.0
    base -= max(within_1km - nearby_500m, 0) * 3.0
    return _clamp(base)


def _score_walkability(v):
    return _clamp(v) if v else 60.0


def _score_visibility(corner, street_visibility):
    base = _clamp(street_visibility or 65.0)
    if corner: base = min(100.0, base + 10.0)
    return base


def _score_density_signal(apartment_pct, students, hotels):
    base = 50.0
    if apartment_pct >= 0.45: base += min((apartment_pct - 0.45) * 100, 25.0)
    if students >= 500: base += min(students / 200, 15.0)
    if hotels >= 1: base += min(hotels * 1.5, 10.0)
    return _clamp(base)


def _score_economics(economics: Dict[str, Any]) -> Dict[str, Any]:
    payback = economics.get("payback_years")
    margin = economics.get("operating_margin") or 0.0
    yield_pct = economics.get("yield_pct")
    ebitda = economics.get("ebitda_eur") or 0.0
    irr = economics.get("irr_estimate_pct")

    if ebitda <= 0 or payback is None:
        return {"score": 25.0, "drivers": ["ebitda_negative_or_unknown"]}

    payback_score = 100.0
    if payback >= 12: payback_score = 20.0
    elif payback >= 9: payback_score = 40.0
    elif payback >= 7: payback_score = 60.0
    elif payback >= 5: payback_score = 78.0
    elif payback >= 3.5: payback_score = 90.0

    margin_score = _clamp(margin * 220.0)
    yield_score = _clamp((yield_pct or 0.0) * 350.0)
    irr_score = _clamp((irr or 0.0) * 4.0)

    blended = payback_score * 0.40 + margin_score * 0.25 + yield_score * 0.25 + irr_score * 0.10

    drivers = []
    if payback <= 5: drivers.append("fast_payback")
    if margin >= 0.30: drivers.append("healthy_margin")
    if (yield_pct or 0) >= 0.18: drivers.append("strong_yield")
    if (irr or 0) >= 15: drivers.append("attractive_irr")
    if not drivers: drivers.append("economics_mid_band")

    return {"score": round(blended, 2), "drivers": drivers}


def _score_physical_fit(*, floor_area_m2, ceiling_height, has_water, has_gas,
                        has_drainage, has_3phase_power, ground_floor, loading_access,
                        biz: BusinessProfile) -> Dict[str, Any]:
    score = 50.0
    drivers: List[str] = []

    ideal = biz.ideal_floor_area_m2
    if floor_area_m2 <= 0:
        drivers.append("floor_area_unknown")
    elif floor_area_m2 < biz.min_viable_floor_area_m2:
        score -= 20; drivers.append("undersized_unit")
    elif floor_area_m2 <= biz.max_recommended_floor_area_m2:
        proximity = 1.0 - abs(floor_area_m2 - ideal) / max(ideal, 1.0)
        score += 18.0 * max(proximity, 0.4)
        drivers.append("right_sized_unit")
    elif floor_area_m2 <= biz.hard_max_floor_area_m2:
        score += 4; drivers.append("slightly_oversized_unit")
    else:
        score -= 12; drivers.append("oversized_unit_higher_capex")

    if ceiling_height and ceiling_height >= 2.7: score += 4
    elif ceiling_height and ceiling_height < 2.4: score -= 6; drivers.append("low_ceiling")

    if has_water: score += 6
    else: score -= 8; drivers.append("no_existing_water_supply")
    if has_gas: score += 4
    if has_drainage: score += 5
    else: score -= 7; drivers.append("no_drainage")
    if has_3phase_power: score += 6
    else: drivers.append("requires_3phase_upgrade")
    if ground_floor: score += 8
    else: score -= 10; drivers.append("upper_floor_access_risk")
    if loading_access: score += 2

    return {"score": _clamp(score), "drivers": drivers or ["fit_standard"]}


def _score_preferred_market(location, biz: BusinessProfile):
    matched = location.get("matched_preferred_neighbourhood")
    if location.get("in_preferred_market") or matched:
        return {"bonus": 15.0, "matched": matched or "preferred_market", "reason": "operator_target_market"}
    if biz.target_city and str(location.get("city") or "").lower().startswith(biz.target_city.lower()):
        return {"bonus": 5.0, "matched": biz.target_city, "reason": "target_city_match"}
    return {"bonus": 0.0, "matched": None, "reason": None}


def _score_demographic_targeting(*, apartment_pct, population_density, income_eur,
                                  renter_pct, small_housing_pct, biz: BusinessProfile):
    score = 50.0
    drivers: List[str] = []

    lo, hi = biz.target_income_band_eur
    if lo <= income_eur <= hi:
        score += 14; drivers.append("income_in_target_band")
    elif income_eur > 0:
        score -= min(abs(income_eur - (lo + hi) / 2) / 3000.0, 10.0)

    if biz.target_population_density_min <= population_density <= biz.target_population_density_max:
        score += 12; drivers.append("density_in_target_band")

    if apartment_pct >= biz.target_renter_pct_min:
        score += 10; drivers.append("apartment_dominant_neighbourhood")
    if renter_pct is not None and renter_pct >= biz.target_renter_pct_min:
        score += 8; drivers.append("renter_majority")
    if small_housing_pct is not None and small_housing_pct >= biz.target_small_housing_pct_min:
        score += 8; drivers.append("small_housing_stock")

    return {"score": _clamp(score), "drivers": drivers or ["demographics_unknown"]}


def _score_secondary_revenue_potential(*, economics, extracted, location):
    score = 40.0; drivers: List[str] = []
    secondary_total = float(economics.get("secondary_revenue_eur") or 0.0)
    primary_total = float(economics.get("year1_revenue_eur") or 0.0) or 1.0
    ratio = secondary_total / primary_total
    if ratio >= 0.25: score += 35; drivers.append("strong_secondary_revenue")
    elif ratio >= 0.15: score += 22; drivers.append("solid_secondary_revenue")
    elif ratio >= 0.07: score += 12; drivers.append("modest_secondary_revenue")

    if extracted.get("corner_unit"): score += 8; drivers.append("corner_unit_extra_frontage")
    if extracted.get("loading_access"): score += 4; drivers.append("loading_access_for_drop_off")
    if int(location.get("hotels_within_500m") or 0) >= 3: score += 6; drivers.append("nearby_hotel_demand")
    if int(location.get("students_within_1km") or 0) >= 800: score += 4; drivers.append("student_density")

    return {"score": _clamp(score), "drivers": drivers or ["secondary_revenue_limited"]}


def _confidence(filled_fields: int, thresholds):
    if filled_fields >= thresholds.high_confidence_min_fields: band = "high"
    elif filled_fields <= thresholds.low_confidence_max_fields: band = "low"
    else: band = "medium"
    pct = round(min(100.0, filled_fields / 12.0 * 100.0), 1)
    return {"band": band, "pct": pct, "fields_present": filled_fields}


def _verdict_from_score(score, thresholds):
    if score >= thresholds.approved_min: return "EXCELLENT OPPORTUNITY"
    if score >= thresholds.manual_review_min: return "MANUAL REVIEW"
    return "REJECT"


def _deal_status_from_score(score, thresholds):
    if score >= thresholds.approved_min: return "approved_candidate"
    if score >= thresholds.manual_review_min: return "manual_review"
    return "rejected"


def _classification(score, economics, location, physical_block, competition):
    if score >= 90: return "TROPHY ASSET"
    if score >= 80: return "CORE PLUS"
    if score >= 70: return "VALUE-ADD"
    if score >= 60: return "OPPORTUNISTIC"
    if score >= 50: return "FURTHER DUE DILIGENCE"
    if competition < 30: return "OVERSATURATED MARKET"
    if (economics.get("payback_years") or 99) > 9: return "WEAK ECONOMICS"
    if physical_block["score"] < 35: return "PHYSICAL FIT FAIL"
    return "DOES NOT MEET THRESHOLDS"


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
def score_property(payload: Dict[str, Any], *, overrides: Optional[Dict[str, Any]] = None,
                   filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    extracted = dict(payload.get("extracted") or {})
    location = dict(payload.get("location") or {})
    economics = dict(payload.get("economics") or {})
    filters = dict(filters or {})

    assumptions = merge_overrides(default_assumptions(), overrides)
    baseline = assumptions.location_baseline
    weights = assumptions.scoring_weights
    thresholds = assumptions.thresholds
    biz = assumptions.business_profile

    pop_density = _safe_float(location.get("population_density_per_km2"), baseline.population_density_per_km2)
    income = _safe_float(location.get("household_income_eur"), baseline.median_household_income_eur)
    apartment_pct = _safe_float(location.get("apartment_density_pct"), baseline.apartment_density_pct)
    students = _safe_int(location.get("students_within_1km"), baseline.students_within_1km)
    hotels = _safe_int(location.get("hotels_within_500m"), baseline.hotels_within_500m)
    universities = _safe_int(location.get("universities_within_2km"), baseline.universities_within_2km)
    nearby = _safe_int(location.get("nearby_laundromats_within_500m"), baseline.nearby_laundromats_within_500m)
    competitors = _safe_int(location.get("competitors_within_1km"), baseline.competitors_within_1km)
    walkability = _safe_float(location.get("walkability_score_0_100"), baseline.walkability_score_0_100)
    night_safety = _safe_float(location.get("night_safety_0_100"), baseline.night_safety_0_100)
    growth = _safe_float(location.get("growth_potential_0_100"), 60.0)
    visibility = _safe_float(location.get("street_visibility_0_100"), 65.0)
    corner = bool(location.get("corner_unit") or extracted.get("corner_unit"))

    population_score = _score_population_density(pop_density)
    income_score = _score_income(income)
    walkability_score = _score_walkability(walkability)
    visibility_score = _score_visibility(corner, visibility)
    demand_signal_score = _score_density_signal(apartment_pct, students, hotels)
    night_safety_score = _clamp(night_safety) if night_safety else 60.0
    growth_score = _clamp(growth)
    university_score = _clamp(60.0 + min(universities, 4) * 10.0)
    public_transport_score = _clamp(location.get("public_transport_score_0_100", 70))

    location_component = (
        population_score * 0.20
        + income_score * 0.15
        + walkability_score * 0.10
        + visibility_score * 0.12
        + demand_signal_score * 0.16
        + night_safety_score * 0.08
        + growth_score * 0.09
        + university_score * 0.05
        + public_transport_score * 0.05
    )

    competition_component = _score_competition(nearby, competitors)
    economics_block = _score_economics(economics)
    floor_area_for_fit = _safe_float(economics.get("floor_area_m2") or extracted.get("floor_area_m2"))
    physical_block = _score_physical_fit(
        floor_area_m2=floor_area_for_fit,
        ceiling_height=_safe_float(extracted.get("ceiling_height")),
        has_water=bool(extracted.get("water_available", True)),
        has_gas=bool(extracted.get("gas_available", True)),
        has_drainage=bool(extracted.get("drainage_available", True)),
        has_3phase_power=bool(extracted.get("three_phase_power", False)),
        ground_floor=bool(extracted.get("ground_floor", True)),
        loading_access=bool(extracted.get("loading_access", False)),
        biz=biz,
    )

    preferred = _score_preferred_market(location, biz)
    location_component = _clamp(location_component + preferred["bonus"])

    demographic_block = _score_demographic_targeting(
        apartment_pct=apartment_pct,
        population_density=pop_density,
        income_eur=income,
        renter_pct=_safe_float(location.get("renter_pct"), 0.0) or None,
        small_housing_pct=_safe_float(location.get("small_housing_pct"), 0.0) or None,
        biz=biz,
    )
    location_component = _clamp(location_component * 0.80 + demographic_block["score"] * 0.20)

    secondary_block = _score_secondary_revenue_potential(
        economics=economics, extracted=extracted, location=location
    )

    risk_component = 75.0
    risk_drivers: List[str] = []
    if extracted.get("requires_change_of_use"): risk_component -= 15; risk_drivers.append("requires_change_of_use_permit")
    if extracted.get("noise_restriction"): risk_component -= 10; risk_drivers.append("noise_restriction")
    if extracted.get("structural_issue_flag"): risk_component -= 20; risk_drivers.append("possible_structural_issue")
    if extracted.get("flood_risk_flag"): risk_component -= 12; risk_drivers.append("flood_risk")
    if night_safety and night_safety < 45: risk_component -= 10; risk_drivers.append("low_night_safety")
    risk_component = _clamp(risk_component)

    secondary_weight = getattr(weights, "secondary_revenue", 0.0) or 0.0
    total_weight = (
        weights.location + weights.economics + weights.physical_fit
        + weights.competition + weights.risk + secondary_weight
    ) or 1.0
    final = (
        location_component * (weights.location / total_weight)
        + economics_block["score"] * (weights.economics / total_weight)
        + physical_block["score"] * (weights.physical_fit / total_weight)
        + competition_component * (weights.competition / total_weight)
        + risk_component * (weights.risk / total_weight)
        + secondary_block["score"] * (secondary_weight / total_weight)
    )
    final_score = int(round(_clamp(final)))

    filled = sum(1 for k in CRITICAL_LOCATION_FIELDS if location.get(k) not in (None, "", 0))
    confidence = _confidence(filled, thresholds)

    verdict = _verdict_from_score(final_score, thresholds)
    deal_status = _deal_status_from_score(final_score, thresholds)
    notes: List[str] = []

    max_size = _safe_float(filters.get("max_size_sqm"), 0.0)
    if max_size > 0 and floor_area_for_fit > max_size * 1.05:
        if deal_status == "approved_candidate":
            deal_status = "manual_review"; verdict = "MANUAL REVIEW"
        notes.append(f"property_exceeds_max_size_{int(max_size)}m2")

    if confidence["band"] == "low" and deal_status == "rejected":
        deal_status = "manual_review"; verdict = "MANUAL REVIEW"
        notes.append("promoted_to_review_due_to_low_confidence")

    classification = _classification(final_score, economics, location, physical_block, competition_component)

    return {
        "score": final_score,
        "verdict": verdict,
        "classification": classification,
        "deal_status": deal_status,
        "confidence": confidence,
        "auto_scores": {
            "location_score": round(location_component, 2),
            "economics_score": round(economics_block["score"], 2),
            "physical_fit_score": round(physical_block["score"], 2),
            "competition_score": round(competition_component, 2),
            "risk_score": round(risk_component, 2),
            "secondary_revenue_score": round(secondary_block["score"], 2),
            "demographic_targeting_score": round(demographic_block["score"], 2),
            "sub_components": {
                "population": round(population_score, 2),
                "income": round(income_score, 2),
                "walkability": round(walkability_score, 2),
                "visibility": round(visibility_score, 2),
                "demand_signal": round(demand_signal_score, 2),
                "night_safety": round(night_safety_score, 2),
                "growth": round(growth_score, 2),
                "universities": round(university_score, 2),
                "public_transport": round(public_transport_score, 2),
            },
        },
        "preferred_market": preferred,
        "drivers": {
            "economics": economics_block["drivers"],
            "physical": physical_block["drivers"],
            "risk": risk_drivers,
            "demographics": demographic_block["drivers"],
            "secondary_revenue": secondary_block["drivers"],
        },
        "notes": notes,
        "weights_used": {
            "location": weights.location,
            "economics": weights.economics,
            "physical_fit": weights.physical_fit,
            "competition": weights.competition,
            "risk": weights.risk,
            "secondary_revenue": secondary_weight,
        },
        "thresholds": {
            "approved_min": thresholds.approved_min,
            "manual_review_min": thresholds.manual_review_min,
        },
        "applied_filters": filters,
    }
