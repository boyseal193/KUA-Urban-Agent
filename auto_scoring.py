# auto_scoring.py

from typing import Dict, Any


def score_location(extracted: Dict[str, Any]) -> int:
    neighbourhood = (extracted.get("neighbourhood") or "").lower()

    premium = [
        "eixample",
        "gracia",
        "les corts",
        "sant gervasi",
        "sarria",
        "poblenou",
    ]

    strong = [
        "sants",
        "clot",
        "guinardo",
        "horta",
        "sant marti",
    ]

    weak = [
        "trinitat vella",
        "nou barris",
        "besos",
        "zona franca",
    ]

    risky = [
        "raval",
    ]

    score = 10

    for area in premium:
        if area in neighbourhood:
            score = 20

    for area in strong:
        if area in neighbourhood:
            score = 17

    for area in weak:
        if area in neighbourhood:
            score = 14

    for area in risky:
        if area in neighbourhood:
            score = 10

    return score


def score_building(extracted: Dict[str, Any]) -> int:
    score = 0

    gba_m2 = extracted.get("gba_m2") or 0
    ceiling_height = extracted.get("ceiling_height")
    loading_access = extracted.get("loading_access")
    access_type = (extracted.get("access_type") or "").lower()
    floor_level = (extracted.get("floor_level") or "").lower()
    description = (extracted.get("description") or "").lower()

    # Size
    if gba_m2 >= 250:
        score += 8
    elif gba_m2 >= 200:
        score += 6
    else:
        score += 3

    # Ceiling height
    if ceiling_height:
        if ceiling_height >= 3.5:
            score += 6
        elif ceiling_height >= 3.0:
            score += 5
        elif ceiling_height >= 2.7:
            score += 3
        else:
            score -= 2
    else:
        score += 2

    # Ground floor
    if "ground" in floor_level or "street" in floor_level:
        score += 5

    # Access logic
    if loading_access:
        score += 6

    elif (
        "street" in access_type
        or "vehicle" in access_type
        or "direct access" in access_type
        or "street level" in access_type
    ):
        score += 4

    elif "pedestrian" in access_type:
        score += 1

    else:
        score -= 2

    # Open-plan bonus
    if "open-plan" in description or "open plan" in description:
        score += 3

    # Natural light bonus
    if (
        "natural light" in description
        or "skylight" in description
        or "skylights" in description
    ):
        score += 1

    # Penalize mezzanine/multi-floor
    if (
        "mezzanine" in floor_level
        or "two floors" in description
        or "two-floor" in description
    ):
        score -= 6

    return max(min(score, 25), 0)


def score_economics(economics: Dict[str, Any]) -> int:
    score = 0

    true_ebitda_yield = economics.get("true_ebitda_yield")
    payback_years = economics.get("true_payback_years")
    margin = economics.get("margin") or 0

    if true_ebitda_yield:
        if true_ebitda_yield >= 0.15:
            score += 25
        elif true_ebitda_yield >= 0.12:
            score += 22
        elif true_ebitda_yield >= 0.10:
            score += 18
        elif true_ebitda_yield >= 0.08:
            score += 14
        elif true_ebitda_yield >= 0.06:
            score += 10
        else:
            score += 4

    if payback_years:
        if payback_years <= 7:
            score += 5
        elif payback_years <= 10:
            score += 4
        elif payback_years <= 15:
            score += 2
        else:
            score -= 2

    if margin >= 0.70:
        score += 3
    elif margin >= 0.50:
        score += 1
    else:
        score -= 4

    return max(min(score, 30), 0)


def score_risk(
    extracted: Dict[str, Any],
    economics: Dict[str, Any]
) -> int:
    score = 15

    ceiling_height = extracted.get("ceiling_height")
    loading_access = extracted.get("loading_access")
    margin = economics.get("margin") or 0

    if not ceiling_height:
        score -= 2

    if not loading_access:
        score -= 2

    if margin < 0.25:
        score -= 10

    return max(min(score, 15), 0)


def score_strategic_fit(extracted: Dict[str, Any]) -> int:
    score = 0

    gba_m2 = extracted.get("gba_m2") or 0
    building_type = (
        extracted.get("building_type") or ""
    ).lower()

    if gba_m2 >= 250:
        score += 5
    else:
        score += 3

    if (
        "commercial" in building_type
        or "warehouse" in building_type
        or "industrial" in building_type
    ):
        score += 5

    return max(min(score, 10), 0)


def classify_deal(total_score: int) -> Dict[str, str]:
    if total_score >= 80:
        return {
            "verdict": "YES",
            "classification": "CORE",
        }

    elif total_score >= 65:
        return {
            "verdict": "CONDITIONAL YES",
            "classification": "CORE — DUE DILIGENCE REQUIRED",
        }

    elif total_score >= 55:
        return {
            "verdict": "WEAK",
            "classification": "VALUE-ADD / MANUAL REVIEW",
        }

    return {
        "verdict": "NO",
        "classification": "REJECT",
    }


def generate_deal_killer(
    extracted: Dict[str, Any],
    economics: Dict[str, Any]
) -> str | None:
    margin = economics.get("margin") or 0
    floor_level = (
        extracted.get("floor_level") or ""
    ).lower()

    if margin < 0.25:
        return "EBITDA margin below 25%"

    if (
        "mezzanine" in floor_level
        or "multiple floors" in floor_level
    ):
        return "Multi-floor layout without proper logistics"

    return None


def generate_due_diligence_flags(
    extracted: Dict[str, Any],
    economics: Dict[str, Any]
) -> list[str]:
    flags = []

    if not extracted.get("ceiling_height"):
        flags.append(
            "Ceiling height missing — contact agent for confirmation"
        )

    if not extracted.get("loading_access"):
        flags.append(
            "Direct loading access not confirmed — verify curbside loading practicality"
        )

    true_ebitda_yield = economics.get("true_ebitda_yield")

    if (
        true_ebitda_yield is not None
        and true_ebitda_yield < 0.08
    ):
        flags.append(
            "True EBITDA yield is weak — negotiate acquisition price or improve revenue assumptions"
        )

    return flags


def score_property(
    extracted: Dict[str, Any],
    economics: Dict[str, Any]
) -> Dict[str, Any]:

    location_score = score_location(extracted)

    building_score = score_building(extracted)

    economics_score = score_economics(economics)

    risk_score = score_risk(
        extracted,
        economics,
    )

    strategic_fit_score = score_strategic_fit(
        extracted
    )

    total_score = (
        location_score
        + building_score
        + economics_score
        + risk_score
        + strategic_fit_score
    )

    classification = classify_deal(total_score)

    deal_killer = generate_deal_killer(
        extracted,
        economics,
    )

    due_diligence_flags = generate_due_diligence_flags(
        extracted,
        economics,
    )

    return {
        "score": total_score,
        "verdict": classification["verdict"],
        "classification": classification["classification"],
        "deal_killer": deal_killer,
        "due_diligence_flags": due_diligence_flags,
        "auto_scores": {
            "location_score": location_score,
            "building_score": building_score,
            "economics_score": economics_score,
            "risk_score": risk_score,
            "strategic_fit_score": strategic_fit_score,
        },
    }


# BACKWARDS COMPATIBILITY WRAPPER
def calculate_auto_scores(extracted, economics):
    return score_property(extracted, economics)