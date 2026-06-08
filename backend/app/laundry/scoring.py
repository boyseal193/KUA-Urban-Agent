"""
Laundromat opportunity scoring engine.

Produces a 0 – 100 score with full transparency on every component, plus the
companion ``verdict`` and ``deal_status`` buckets:

* ``>= 75``  approved_candidate / "EXCELLENT OPPORTUNITY"
* ``50-74``  manual_review     / "FURTHER REVIEW"
* ``< 50``   rejected          / "REJECT"

Missing fields never auto-reject the deal — they decay confidence instead. The
philosophy: real-world good opportunities should land mostly in *manual_review*
because operators always need to verify on the ground.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.laundry.assumptions import (
    LaundryAssumptions,
    default_assumptions,
    merge_overrides,
)


CRITICAL_LOCATION_FIELDS = [
    "population_density_per_km2",
    "household_income_eur",
    "walkability_score",
    "nearby_laundromats_within_500m",
    "competitors_within_1km",
    "apartment_density_pct",
    "students_within_1km",
    "street_visibility_0_100",
    "night_safety_0_100",
    "growth_potential_0_100",
]


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _score_population_density(value: float) -> float:
    """Sweet spot 12k – 25k people/km². Below 6k or above 35k is penalised."""
    if value <= 0:
        return 40.0
    if value < 6_000:
        return 35.0
    if value < 10_000:
        return 55.0
    if value < 16_000:
        return 82.0
    if value < 25_000:
        return 92.0
    if value < 35_000:
        return 78.0
    return 60.0


def _score_income(value: float) -> float:
    """Laundromats win mid-market: too poor → no spend, too rich → in-home laundry."""
    if value <= 0:
        return 45.0
    if value < 14_000:
        return 50.0
    if value < 22_000:
        return 80.0
    if value < 38_000:
        return 88.0
    if value < 55_000:
        return 70.0
    return 55.0


def _score_competition(nearby_500m: int, within_1km: int) -> float:
    base = 100.0
    base -= min(nearby_500m, 8) * 9.0
    base -= max(within_1km - nearby_500m, 0) * 3.0
    return _clamp(base, 0.0, 100.0)


def _score_walkability(value: float) -> float:
    return _clamp(value, 0.0, 100.0) if value else 60.0


def _score_visibility(corner: bool, street_visibility: float) -> float:
    base = _clamp(street_visibility or 65.0, 0.0, 100.0)
    if corner:
        base = min(100.0, base + 10.0)
    return base


def _score_density_signal(apartment_pct: float, students: int, hotels: int) -> float:
    """High share of apartment dwellers + tourists + students = laundry demand."""
    base = 50.0
    if apartment_pct >= 0.45:
        base += min((apartment_pct - 0.45) * 100, 25.0)
    if students >= 500:
        base += min(students / 200, 15.0)
    if hotels >= 1:
        base += min(hotels * 1.5, 10.0)
    return _clamp(base, 0.0, 100.0)


def _score_economics(economics: Dict[str, Any]) -> Dict[str, Any]:
    """Convert raw economics into a 0-100 sub-score + drivers."""
    payback = economics.get("payback_years")
    margin = economics.get("operating_margin") or 0.0
    yield_pct = economics.get("yield_pct")
    ebitda = economics.get("ebitda_eur") or 0.0
    irr = economics.get("irr_estimate_pct")

    if ebitda <= 0 or payback is None:
        return {
            "score": 25.0,
            "drivers": ["ebitda_negative_or_unknown"],
        }

    payback_score = 100.0
    if payback >= 12:
        payback_score = 20.0
    elif payback >= 9:
        payback_score = 40.0
    elif payback >= 7:
        payback_score = 60.0
    elif payback >= 5:
        payback_score = 78.0
    elif payback >= 3.5:
        payback_score = 90.0

    margin_score = _clamp(margin * 220.0, 0.0, 100.0)
    yield_score = _clamp((yield_pct or 0.0) * 350.0, 0.0, 100.0)
    irr_score = _clamp((irr or 0.0) * 4.0, 0.0, 100.0)

    blended = (
        payback_score * 0.40
        + margin_score * 0.25
        + yield_score * 0.25
        + irr_score * 0.10
    )

    drivers = []
    if payback <= 5:
        drivers.append("fast_payback")
    if margin >= 0.30:
        drivers.append("healthy_margin")
    if (yield_pct or 0) >= 0.18:
        drivers.append("strong_yield")
    if (irr or 0) >= 15:
        drivers.append("attractive_irr")
    if not drivers:
        drivers.append("economics_mid_band")

    return {"score": round(blended, 2), "drivers": drivers}


def _score_physical_fit(
    *,
    floor_area_m2: float,
    ceiling_height: float,
    has_water: bool,
    has_gas: bool,
    has_drainage: bool,
    has_3phase_power: bool,
    ground_floor: bool,
    loading_access: bool,
) -> Dict[str, Any]:
    score = 50.0
    drivers: List[str] = []

    if floor_area_m2 >= 60:
        score += 18
        drivers.append("good_floor_area")
    elif floor_area_m2 >= 40:
        score += 9
    elif floor_area_m2 < 25:
        score -= 22
        drivers.append("undersized_unit")

    if ceiling_height and ceiling_height >= 2.7:
        score += 4
    elif ceiling_height and ceiling_height < 2.4:
        score -= 6
        drivers.append("low_ceiling")

    if has_water:
        score += 6
    else:
        score -= 8
        drivers.append("no_existing_water_supply")
    if has_gas:
        score += 4
    if has_drainage:
        score += 5
    else:
        score -= 7
        drivers.append("no_drainage")
    if has_3phase_power:
        score += 6
    else:
        drivers.append("requires_3phase_upgrade")
    if ground_floor:
        score += 8
    else:
        score -= 10
        drivers.append("upper_floor_access_risk")
    if loading_access:
        score += 2

    return {"score": _clamp(score), "drivers": drivers or ["fit_standard"]}


def _confidence(filled_fields: int, thresholds) -> Dict[str, Any]:
    if filled_fields >= thresholds.high_confidence_min_fields:
        band = "high"
    elif filled_fields <= thresholds.low_confidence_max_fields:
        band = "low"
    else:
        band = "medium"
    pct = round(min(100.0, filled_fields / 12.0 * 100.0), 1)
    return {"band": band, "pct": pct, "fields_present": filled_fields}


def _verdict_from_score(score: int, thresholds) -> str:
    if score >= thresholds.approved_min:
        return "EXCELLENT OPPORTUNITY"
    if score >= thresholds.manual_review_min:
        return "MANUAL REVIEW"
    return "REJECT"


def _deal_status_from_score(score: int, thresholds) -> str:
    if score >= thresholds.approved_min:
        return "approved_candidate"
    if score >= thresholds.manual_review_min:
        return "manual_review"
    return "rejected"


def score_property(
    payload: Dict[str, Any],
    *,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Score a single laundromat opportunity.

    Expects::

        {
            "extracted": {<scraped/normalised property fields>},
            "location": {<demographic + competition inputs>},
            "economics": {<output from app.laundry.economics.calculate_economics>},
        }
    """
    extracted = dict(payload.get("extracted") or {})
    location = dict(payload.get("location") or {})
    economics = dict(payload.get("economics") or {})

    assumptions = merge_overrides(default_assumptions(), overrides)
    baseline = assumptions.location_baseline
    weights = assumptions.scoring_weights
    thresholds = assumptions.thresholds

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
    corner = bool(location.get("corner_unit"))

    # Location sub-scores ---------------------------------------------------
    population_score = _score_population_density(pop_density)
    income_score = _score_income(income)
    walkability_score = _score_walkability(walkability)
    visibility_score = _score_visibility(corner, visibility)
    demand_signal_score = _score_density_signal(apartment_pct, students, hotels)
    night_safety_score = _clamp(night_safety, 0, 100) if night_safety else 60.0
    growth_score = _clamp(growth, 0, 100)
    university_score = _clamp(60.0 + min(universities, 4) * 10.0, 0, 100)
    public_transport_score = _clamp(location.get("public_transport_score_0_100", 70), 0, 100)

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
    physical_block = _score_physical_fit(
        floor_area_m2=_safe_float(economics.get("floor_area_m2") or extracted.get("floor_area_m2")),
        ceiling_height=_safe_float(extracted.get("ceiling_height")),
        has_water=bool(extracted.get("water_available", True)),
        has_gas=bool(extracted.get("gas_available", True)),
        has_drainage=bool(extracted.get("drainage_available", True)),
        has_3phase_power=bool(extracted.get("three_phase_power", False)),
        ground_floor=bool(extracted.get("ground_floor", True)),
        loading_access=bool(extracted.get("loading_access", False)),
    )

    # Risk component: aggregates listing red flags --------------------------
    risk_component = 75.0
    risk_drivers: List[str] = []
    if extracted.get("requires_change_of_use"):
        risk_component -= 15
        risk_drivers.append("requires_change_of_use_permit")
    if extracted.get("noise_restriction"):
        risk_component -= 10
        risk_drivers.append("noise_restriction")
    if extracted.get("structural_issue_flag"):
        risk_component -= 20
        risk_drivers.append("possible_structural_issue")
    if extracted.get("flood_risk_flag"):
        risk_component -= 12
        risk_drivers.append("flood_risk")
    if night_safety and night_safety < 45:
        risk_component -= 10
        risk_drivers.append("low_night_safety")
    risk_component = _clamp(risk_component)

    # Weighted blend --------------------------------------------------------
    total_weight = weights.location + weights.economics + weights.physical_fit + weights.competition + weights.risk
    if total_weight <= 0:
        total_weight = 1.0
    final = (
        location_component * (weights.location / total_weight)
        + economics_block["score"] * (weights.economics / total_weight)
        + physical_block["score"] * (weights.physical_fit / total_weight)
        + competition_component * (weights.competition / total_weight)
        + risk_component * (weights.risk / total_weight)
    )
    final_score = int(round(_clamp(final)))

    # Confidence ------------------------------------------------------------
    filled = sum(1 for k in CRITICAL_LOCATION_FIELDS if location.get(k) not in (None, "", 0))
    confidence = _confidence(filled, thresholds)

    verdict = _verdict_from_score(final_score, thresholds)
    deal_status = _deal_status_from_score(final_score, thresholds)

    # When confidence is low we bump rejects to manual_review so the operator decides.
    if confidence["band"] == "low" and deal_status == "rejected":
        deal_status = "manual_review"
        verdict = "MANUAL REVIEW"
        notes = ["promoted_to_review_due_to_low_confidence"]
    else:
        notes = []

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
        "drivers": {
            "economics": economics_block["drivers"],
            "physical": physical_block["drivers"],
            "risk": risk_drivers,
        },
        "notes": notes,
        "weights_used": {
            "location": weights.location,
            "economics": weights.economics,
            "physical_fit": weights.physical_fit,
            "competition": weights.competition,
            "risk": weights.risk,
        },
        "thresholds": {
            "approved_min": thresholds.approved_min,
            "manual_review_min": thresholds.manual_review_min,
        },
    }


def _classification(
    score: int,
    economics: Dict[str, Any],
    location: Dict[str, Any],
    physical_block: Dict[str, Any],
    competition: float,
) -> str:
    if score >= 90:
        return "TROPHY ASSET"
    if score >= 80:
        return "CORE PLUS"
    if score >= 70:
        return "VALUE-ADD"
    if score >= 60:
        return "OPPORTUNISTIC"
    if score >= 50:
        return "FURTHER DUE DILIGENCE"
    if competition < 30:
        return "OVERSATURATED MARKET"
    if (economics.get("payback_years") or 99) > 9:
        return "WEAK ECONOMICS"
    if physical_block["score"] < 35:
        return "PHYSICAL FIT FAIL"
    return "DOES NOT MEET THRESHOLDS"
