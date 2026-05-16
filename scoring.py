# scoring.py

def reject(reason, flags):
    return {
        "score": 0,
        "verdict": "NO",
        "classification": "REJECT",
        "deal_killer": reason,
        "due_diligence_flags": flags
    }


def score_property(data):
    extracted = data.get("extracted", {}) or {}
    economics = data.get("economics", {}) or {}
    auto_scores = data.get("auto_scores", {}) or {}

    due_diligence_flags = []

    ceiling_height = extracted.get("ceiling_height")
    loading_access = extracted.get("loading_access")
    floor_level = str(extracted.get("floor_level") or "").lower()
    building_type = str(extracted.get("building_type") or "").lower()
    access_type = str(extracted.get("access_type") or "").lower()

    true_yield = economics.get("true_ebitda_yield")
    ebitda_yield = economics.get("ebitda_yield")
    margin = economics.get("margin")
    nra_eff = economics.get("nra_efficiency")
    payback_years = economics.get("true_payback_years") or economics.get("payback_years")

    location_score = auto_scores.get("location_score", 0) or 0
    building_score = auto_scores.get("building_score", 0) or 0
    economics_score = auto_scores.get("economics_score", 0) or 0
    risk_score = auto_scores.get("risk_score", 0) or 0
    strategic_score = auto_scores.get("strategic_fit_score", 0) or 0

    # -------------------------
    # DUE DILIGENCE FLAGS
    # -------------------------

    if not ceiling_height:
        due_diligence_flags.append(
            "Ceiling height missing — contact agent for confirmation"
        )

    if loading_access is False:
        due_diligence_flags.append(
            "Loading access not confirmed — verify whether van loading is possible"
        )

    # -------------------------
    # HARD DEAL KILLERS
    # -------------------------

    if margin is not None and margin < 0.25:
        return reject("EBITDA margin below 25%", due_diligence_flags)

    if nra_eff is not None and nra_eff < 0.70:
        return reject("NRA efficiency below 70%", due_diligence_flags)

    if "residential" in building_type and "commercial" not in building_type:
        return reject("Residential property / wrong use class", due_diligence_flags)

    if "basement" in floor_level and "ground" not in floor_level and "street" not in floor_level:
        return reject("Basement-only property", due_diligence_flags)

    if "mezzanine" in floor_level and loading_access is False and nra_eff is not None and nra_eff < 0.85:
        return reject("Multi-floor layout without proper logistics", due_diligence_flags)

    # -------------------------
    # SCORE BUILD
    # -------------------------

    total_score = (
        location_score
        + building_score
        + economics_score
        + risk_score
        + strategic_score
    )

    # -------------------------
    # ECONOMICS ADJUSTMENTS
    # -------------------------

    if true_yield is not None:
        if true_yield >= 0.08:
            total_score += 8
        elif true_yield >= 0.06:
            total_score += 4
        elif true_yield >= 0.045:
            total_score -= 3
            due_diligence_flags.append(
                "True EBITDA yield is weak — only proceed if price can be negotiated or revenue assumptions improve"
            )
        else:
            total_score -= 12
            due_diligence_flags.append(
                "True EBITDA yield below target — manual review only"
            )

    elif ebitda_yield is not None:
        if ebitda_yield < 0.05:
            total_score -= 10
            due_diligence_flags.append(
                "EBITDA yield below target — manual review only"
            )

    if payback_years is not None:
        if payback_years <= 12:
            total_score += 4
        elif payback_years <= 18:
            total_score -= 2
        else:
            total_score -= 8
            due_diligence_flags.append(
                "Payback period is long — check if acquisition price is too high"
            )

    # -------------------------
    # ACCESS ADJUSTMENTS
    # -------------------------

    has_street_access = (
        "street" in access_type
        or "street" in floor_level
        or "ground" in floor_level
    )

    if loading_access is True:
        total_score += 4
    elif loading_access is False and has_street_access:
        total_score -= 4
        due_diligence_flags.append(
            "Score adjusted: street access exists but loading access is not confirmed"
        )
    elif loading_access is False:
        total_score -= 8
        due_diligence_flags.append(
            "Score adjusted: no loading access confirmed"
        )

    # Ceiling height missing should NOT kill the deal.
    # It is only a DD flag, especially if the deal scores well overall.
    if ceiling_height:
        try:
            height = float(ceiling_height)
            if height >= 3.0:
                total_score += 3
            elif height < 2.4:
                total_score -= 10
                due_diligence_flags.append(
                    "Ceiling height appears low — confirm whether storage conversion is viable"
                )
        except Exception:
            due_diligence_flags.append(
                "Ceiling height format unclear — contact agent for confirmation"
            )

    # -------------------------
    # LOCATION / BUILDING-SPECIFIC ADJUSTMENTS
    # -------------------------

    neighbourhood = str(extracted.get("neighbourhood") or "").lower()

    if "raval" in neighbourhood:
        total_score -= 4
        due_diligence_flags.append(
            "El Raval location risk — check safety, customer perception and loading restrictions"
        )

    if "la marina del prat vermell" in neighbourhood:
        total_score -= 8
        due_diligence_flags.append(
            "Emerging location — demand may be weaker until the area matures"
        )

    if "les corts" in neighbourhood:
        total_score += 2

    if "fort pienc" in neighbourhood:
        total_score += 2

    if "sant martí de provençals" in neighbourhood:
        total_score -= 2

    if "new development" in building_type or "new build" in building_type:
        total_score += 2

    # -------------------------
    # FINAL SCORE CLAMP
    # -------------------------

    total_score = max(0, min(100, int(round(total_score))))

    # -------------------------
    # VERDICT LOGIC
    # -------------------------

    if total_score >= 78:
        verdict = "YES"
        classification = "CORE"
    elif total_score >= 65:
        verdict = "CONDITIONAL YES"
        classification = "CORE — DUE DILIGENCE REQUIRED"
    elif total_score >= 55:
        verdict = "WEAK"
        classification = "VALUE-ADD / MANUAL REVIEW"
    else:
        verdict = "NO"
        classification = "REJECT"

    return {
        "score": total_score,
        "verdict": verdict,
        "classification": classification,
        "deal_killer": None,
        "due_diligence_flags": due_diligence_flags
    }