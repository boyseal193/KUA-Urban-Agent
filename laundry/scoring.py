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
from laundry.normalization import ground_floor_value, laundromat_access_impossible


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
    """Financial-return sub-score (0–100), underwriting-grade and conservative.

    Anchored on EBITDA yield ON TOTAL INVESTMENT (which includes acquisition
    price, transaction taxes, capex and working capital) — NOT on margin, which
    for a BUY is misleadingly high because there is no rent line. Payback,
    margin and downside survivability adjust around that anchor. Negative or
    unknown EBITDA collapses the score; a good yield only reaches the
    manual-review band and needs supporting evidence to approach approval.
    """
    ebitda = _safe_float(economics.get("ebitda_eur"))
    payback = economics.get("payback_years")
    margin = _safe_float(economics.get("operating_margin"))
    # Prefer yield on TOTAL investment; fall back to legacy yield_pct.
    yld = economics.get("ebitda_yield_on_total_pct")
    if yld is None:
        yld = economics.get("yield_pct")
    yld = _safe_float(yld)
    downside_ebitda = economics.get("downside_ebitda_eur")

    if ebitda <= 0 or payback is None:
        return {"score": 12.0, "drivers": ["ebitda_negative_or_unknown"]}

    # --- yield anchor (conservative; 8% -> ~60, 15% -> ~85) --------------
    if yld >= 0.15:
        anchor = 86.0
    elif yld >= 0.12:
        anchor = 76.0
    elif yld >= 0.10:
        anchor = 66.0
    elif yld >= 0.08:
        anchor = 58.0
    elif yld >= 0.065:
        anchor = 48.0
    elif yld >= 0.05:
        anchor = 40.0
    elif yld >= 0.035:
        anchor = 30.0
    elif yld >= 0.02:
        anchor = 22.0
    else:
        anchor = 15.0

    # --- payback modifier ------------------------------------------------
    if payback <= 4:
        anchor += 8
    elif payback <= 6:
        anchor += 3
    elif payback <= 9:
        anchor += 0
    elif payback <= 12:
        anchor -= 8
    else:
        anchor -= 16

    # --- margin modifier (health, not primary) ---------------------------
    if margin >= 0.30:
        anchor += 4
    elif margin >= 0.20:
        anchor += 1
    elif margin >= 0.12:
        anchor += 0
    elif margin >= 0.05:
        anchor -= 6
    else:
        anchor -= 12

    # --- downside survivability -----------------------------------------
    if downside_ebitda is not None and _safe_float(downside_ebitda) <= 0:
        anchor -= 12

    drivers: List[str] = []
    if yld >= 0.12: drivers.append("strong_yield_on_total")
    elif yld >= 0.08: drivers.append("acceptable_yield_on_total")
    else: drivers.append("thin_yield_on_total")
    if payback is not None and payback <= 5: drivers.append("fast_payback")
    if payback is not None and payback > 9: drivers.append("long_payback")
    if margin >= 0.25: drivers.append("healthy_margin")
    if downside_ebitda is not None and _safe_float(downside_ebitda) <= 0:
        drivers.append("downside_ebitda_negative")

    return {"score": round(_clamp(anchor), 2), "drivers": drivers}


def _score_physical_fit(*, floor_area_m2, ceiling_height, has_water, has_gas,
                        has_drainage, has_3phase_power, ground_floor: Optional[bool], loading_access,
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
    if ground_floor is True:
        score += 18
        drivers.append("ground_floor_strong_positive")
    elif ground_floor is False:
        score -= 6
        drivers.append("not_ground_floor_major_warning")
    else:
        score -= 4
        drivers.append("floor_level_unknown_verify_on_site")
    if loading_access: score += 4
    elif ground_floor is False:
        drivers.append("upper_floor_without_loading_access")

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
# Deterministic hard financial gates
# ---------------------------------------------------------------------------
def _gate(name: str, passed: bool, *, actual, threshold, message: str,
          severity: str = "review", mandatory: bool = True) -> Dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "mandatory": bool(mandatory),
        "severity": severity,          # "review" (soft) | "reject" (severe)
        "actual": actual,
        "threshold": threshold,
        "message": message,
    }


def _evaluate_gates(economics: Dict[str, Any], gates, *,
                    acquisition_type: str) -> List[Dict[str, Any]]:
    """Return the full gate list (passed + failed). Deterministic; no AI.

    Only fails on CONFIRMED bad economics. Missing values are handled by the
    confidence cap, not by gates, so we never reject purely for absent data.
    """
    out: List[Dict[str, Any]] = []
    ebitda = economics.get("ebitda_eur")
    downside = economics.get("downside_ebitda_eur")
    payback = economics.get("payback_years")
    margin = _safe_float(economics.get("operating_margin"))
    yld = economics.get("ebitda_yield_on_total_pct")
    if yld is None:
        yld = economics.get("yield_pct")

    if acquisition_type == "rent":
        rtr = economics.get("rent_to_revenue_pct")
        if rtr is not None:
            out.append(_gate(
                "rent_to_revenue", _safe_float(rtr) <= gates.rent_hardfail_rent_to_revenue,
                actual=rtr, threshold=gates.rent_hardfail_rent_to_revenue,
                message="Rent exceeds 35% of revenue — unsustainable",
                severity="reject",
            ))
            out.append(_gate(
                "rent_to_revenue_sustainable", _safe_float(rtr) <= gates.rent_max_rent_to_revenue,
                actual=rtr, threshold=gates.rent_max_rent_to_revenue,
                message="Rent above 25% of revenue — margin pressure",
                severity="review",
            ))
        if ebitda is not None:
            out.append(_gate(
                "positive_ebitda", _safe_float(ebitda) > gates.rent_min_stabilised_ebitda_eur,
                actual=ebitda, threshold=gates.rent_min_stabilised_ebitda_eur,
                message="Stabilised EBITDA is not positive after rent",
                severity="reject",
            ))
        if downside is not None:
            out.append(_gate(
                "downside_ebitda", _safe_float(downside) > gates.rent_min_downside_ebitda_eur,
                actual=downside, threshold=gates.rent_min_downside_ebitda_eur,
                message="Downside case goes EBITDA-negative",
                severity="review",
            ))
        if margin:
            out.append(_gate(
                "min_margin", margin >= gates.rent_min_ebitda_margin,
                actual=margin, threshold=gates.rent_min_ebitda_margin,
                message="EBITDA margin below 12%",
                severity="review",
            ))
        if payback is not None:
            out.append(_gate(
                "fitout_payback", payback <= gates.rent_review_max_payback_years,
                actual=payback, threshold=gates.rent_review_max_payback_years,
                message="Payback on fit-out/equipment too long for a lease",
                severity="review",
            ))
    else:  # buy
        price_per_m2 = economics.get("price_per_m2_eur")
        if ebitda is not None:
            out.append(_gate(
                "positive_ebitda", _safe_float(ebitda) > gates.buy_min_stabilised_ebitda_eur,
                actual=ebitda, threshold=gates.buy_min_stabilised_ebitda_eur,
                message="Stabilised EBITDA is not positive",
                severity="reject",
            ))
        if downside is not None:
            out.append(_gate(
                "downside_ebitda", _safe_float(downside) > gates.buy_min_downside_ebitda_eur,
                actual=downside, threshold=gates.buy_min_downside_ebitda_eur,
                message="Downside case goes EBITDA-negative",
                severity="review",
            ))
        if yld is not None:
            out.append(_gate(
                "ebitda_yield_on_total", _safe_float(yld) >= gates.buy_min_ebitda_yield_on_total,
                actual=yld, threshold=gates.buy_min_ebitda_yield_on_total,
                message="EBITDA yield on total investment below 8% hurdle",
                severity="review",
            ))
        if payback is not None:
            out.append(_gate(
                "payback", payback <= gates.buy_max_payback_years,
                actual=payback, threshold=gates.buy_max_payback_years,
                message="Payback exceeds 6 years",
                severity="review",
            ))
        # Affordability: overpriced per m² is allowed ONLY with stronger yield.
        if price_per_m2 is not None and _safe_float(price_per_m2) > gates.buy_max_price_per_m2_eur:
            out.append(_gate(
                "affordability_price_per_m2",
                _safe_float(yld or 0) >= gates.buy_overpriced_requires_yield,
                actual={"price_per_m2": price_per_m2, "yield": yld},
                threshold={"max_price_per_m2": gates.buy_max_price_per_m2_eur,
                           "required_yield_if_over": gates.buy_overpriced_requires_yield},
                message="Price/m² above market ceiling and yield does not justify the premium",
                severity="review",
            ))

    # Shared approval-margin floor.
    if margin:
        out.append(_gate(
            "approval_margin_floor", margin >= gates.min_ebitda_margin_for_approval,
            actual=margin, threshold=gates.min_ebitda_margin_for_approval,
            message="EBITDA margin below 15% approval floor",
            severity="review",
        ))
    return out


def _critical_financial_fields_present(economics: Dict[str, Any], acquisition_type: str) -> bool:
    if _safe_float(economics.get("floor_area_m2")) <= 0:
        return False
    if _safe_float(economics.get("ebitda_eur")) == 0 and economics.get("payback_years") is None:
        return False
    if acquisition_type == "rent":
        return _safe_float(economics.get("rent_cost_eur")) > 0
    return _safe_float(economics.get("acquisition_cost_eur")) > 0


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
    ground_floor = ground_floor_value(extracted)
    physical_block = _score_physical_fit(
        floor_area_m2=floor_area_for_fit,
        ceiling_height=_safe_float(extracted.get("ceiling_height")),
        has_water=bool(extracted.get("water_available", True)),
        has_gas=bool(extracted.get("gas_available", True)),
        has_drainage=bool(extracted.get("drainage_available", True)),
        has_3phase_power=bool(extracted.get("three_phase_power", False)),
        ground_floor=ground_floor,
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
    if ground_floor is False:
        risk_component -= 12
        risk_drivers.append("not_ground_floor_major_access_warning")
    elif ground_floor is None:
        risk_component -= 6
        risk_drivers.append("floor_level_unknown_manual_verification")
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

    acquisition_type = (economics.get("acquisition_type") or "").lower()
    if acquisition_type not in ("buy", "rent"):
        acquisition_type = "buy"

    caps = assumptions.confidence_caps
    gates_cfg = assumptions.gates
    notes: List[str] = []

    # --- Confidence caps: missing data is a CEILING, never additive ------
    score_caps: List[Dict[str, Any]] = []
    if not _critical_financial_fields_present(economics, acquisition_type):
        if final_score > caps.critical_missing_max_score:
            score_caps.append({"reason": "critical_financial_fields_missing",
                               "cap": caps.critical_missing_max_score})
            final_score = caps.critical_missing_max_score
        notes.append("critical_financial_fields_missing_score_capped")
    if filled < caps.operational_missing_field_threshold and final_score > caps.operational_missing_max_score:
        score_caps.append({"reason": "several_operational_fields_missing",
                           "cap": caps.operational_missing_max_score})
        final_score = caps.operational_missing_max_score
        notes.append("operational_fields_missing_score_capped")

    # --- Deterministic hard financial gates -----------------------------
    gates = _evaluate_gates(economics, gates_cfg, acquisition_type=acquisition_type)
    gate_failures = [g for g in gates if g["mandatory"] and not g["passed"]]
    reject_failures = [g for g in gate_failures if g["severity"] == "reject"]

    verdict = _verdict_from_score(final_score, thresholds)
    deal_status = _deal_status_from_score(final_score, thresholds)

    max_size = _safe_float(filters.get("max_size_sqm"), 0.0)
    if max_size > 0 and floor_area_for_fit > max_size * 1.05:
        if deal_status == "approved_candidate":
            deal_status = "manual_review"; verdict = "MANUAL REVIEW"
        notes.append(f"property_exceeds_max_size_{int(max_size)}m2")

    if ground_floor is None:
        if deal_status == "approved_candidate":
            deal_status = "manual_review"
            verdict = "MANUAL REVIEW"
        notes.append("floor_level_unknown_requires_verification")
    elif ground_floor is False:
        if deal_status == "approved_candidate":
            deal_status = "manual_review"
            verdict = "MANUAL REVIEW"
        notes.append("not_ground_floor_requires_manual_review")
        if laundromat_access_impossible(extracted) and deal_status != "manual_review":
            deal_status = "manual_review"
            verdict = "MANUAL REVIEW"
            notes.append("upper_floor_access_limited_not_auto_rejected")

    # --- Gate-driven demotion — deterministic economics control verdict --
    if reject_failures:
        deal_status = "rejected"; verdict = "REJECT"
        notes.extend(f"gate_failed_{g['name']}" for g in reject_failures)
    elif gate_failures:
        if deal_status == "approved_candidate":
            deal_status = "manual_review"; verdict = "MANUAL REVIEW"
        notes.extend(f"gate_failed_{g['name']}" for g in gate_failures)

    # Low confidence never auto-rejects — promote to review so a human decides.
    if confidence["band"] == "low" and deal_status == "rejected" and not reject_failures:
        deal_status = "manual_review"; verdict = "MANUAL REVIEW"
        notes.append("promoted_to_review_due_to_low_confidence")

    # --- Approval also requires confidence + surviving downside ----------
    downside_ebitda = economics.get("downside_ebitda_eur")
    approval_blockers: List[str] = []
    if deal_status == "approved_candidate":
        if confidence["pct"] < caps.min_confidence_pct_for_approval:
            approval_blockers.append("confidence_below_approval_minimum")
        if downside_ebitda is not None and _safe_float(downside_ebitda) <= 0:
            approval_blockers.append("downside_ebitda_not_positive")
        if approval_blockers:
            deal_status = "manual_review"; verdict = "MANUAL REVIEW"
            notes.extend(approval_blockers)

    # --- Four-tier explainable verdict -----------------------------------
    if deal_status == "approved_candidate":
        verdict_detail = "APPROVED"
    elif deal_status == "rejected":
        verdict_detail = "REJECT"
    elif final_score >= thresholds.approved_min and not reject_failures:
        # Score qualifies but a soft gate / confidence / downside condition
        # blocks unconditional approval — state the conditions.
        verdict_detail = "CONDITIONAL_APPROVAL"
    else:
        verdict_detail = "MANUAL_REVIEW"

    classification = _classification(final_score, economics, location, physical_block, competition_component)

    financial_summary = {
        "acquisition_type": acquisition_type,
        "asking_price_eur": economics.get("acquisition_cost_eur"),
        "annual_rent_eur": economics.get("rent_cost_eur"),
        "price_per_m2_eur": economics.get("price_per_m2_eur"),
        "rent_per_m2_month_eur": economics.get("rent_per_m2_month_eur"),
        "transaction_costs_eur": economics.get("acquisition_transaction_cost_eur"),
        "total_investment_eur": economics.get("total_investment_eur"),
        "expected_revenue_eur": economics.get("expected_revenue_eur"),
        "ebitda_eur": economics.get("ebitda_eur"),
        "downside_ebitda_eur": economics.get("downside_ebitda_eur"),
        "ebitda_margin": economics.get("operating_margin"),
        "ebitda_yield_on_total_pct": economics.get("ebitda_yield_on_total_pct"),
        "ebitda_yield_on_price_pct": economics.get("ebitda_yield_on_price_pct"),
        "downside_yield_pct": economics.get("downside_yield_pct"),
        "payback_years": economics.get("payback_years"),
        "rent_to_revenue_pct": economics.get("rent_to_revenue_pct"),
    }

    sub_scores = {
        "financial_return": round(economics_block["score"], 2),
        "location_demand": round(location_component, 2),
        "operational_feasibility": round(competition_component, 2),
        "physical_suitability": round(physical_block["score"], 2),
        "risk": round(risk_component, 2),
        "data_confidence": confidence["pct"],
    }

    return {
        "score": final_score,
        "verdict": verdict,
        "verdict_detail": verdict_detail,
        "classification": classification,
        "deal_status": deal_status,
        "confidence": confidence,
        "scoring_version": assumptions.scoring_version,
        "sub_scores": sub_scores,
        "gates": gates,
        "gate_failures": [g["name"] for g in gate_failures],
        "score_caps": score_caps,
        "financial_summary": financial_summary,
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
