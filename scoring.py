"""K.U.A. self-storage final scoring orchestrator (v3).

Sits on top of ``auto_scoring`` (six financial-led sub-scores) and:

1. Computes a financial-return-led weighted base (0–100).
2. Applies CONFIDENCE CAPS — missing data is a ceiling, never additive points.
3. Runs DETERMINISTIC HARD GATES (separate buy vs rent) — a deal that fails a
   mandatory gate cannot be Approved regardless of score.
4. Runs the strict (rare) physical/legal reject screen.
5. Emits a four-tier explainable verdict:
       REJECT · MANUAL REVIEW · CONDITIONAL APPROVAL · APPROVED
   plus legacy ``verdict`` (YES/MANUAL REVIEW/NO), ``deal_status`` and
   ``deal_killer`` so existing persistence/exports/frontend keep working.

Independent of the laundromat engine — no shared formula.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from auto_scoring import (
    CATEGORY_WEIGHTS,
    calculate_category_scores,
    compute_confidence,
    weighted_base,
)
from storage_assumptions import default_assumptions, merge_overrides


def _clamp(value: float, lo: float = 0, hi: float = 100) -> int:
    return int(round(max(lo, min(hi, value))))


def _f(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Due-diligence flags (missing data => flag, never a hard reject)
# ---------------------------------------------------------------------------
def _collect_due_diligence_flags(extracted, economics, confidence) -> List[str]:
    flags: List[str] = []
    add = flags.append
    if not _f(extracted.get("ceiling_height")):
        add("Ceiling height not confirmed — needed to underwrite rackable NRA")
    if extracted.get("loading_access") is None:
        add("Loading/access not confirmed — verify vehicle/curbside access")
    if not extracted.get("access_type"):
        add("Access type unknown — confirm street/vehicle access")
    if extracted.get("fire_compliance") is None and not extracted.get("fire_risk_flag"):
        add("Fire compliance evidence missing — confirm code compliance for storage use")
    building_type = (extracted.get("building_type") or "").lower()
    if "residential" in building_type and "commercial" not in building_type and "mixed" not in building_type:
        add("Building flagged residential — confirm zoning permits storage use")
    yld = _f(economics.get("true_ebitda_yield")) or _f(economics.get("ebitda_yield"))
    if yld is not None and yld < 0.055:
        add(f"True EBITDA yield {yld:.1%} is below the 5.5% review floor — only proceed if price can move")
    if _f(economics.get("downside_ebitda_eur")) is not None and _f(economics.get("downside_ebitda_eur")) <= 0:
        add("Downside case goes EBITDA-negative — stress-test occupancy and pricing")
    if confidence["band"] == "low":
        add("Extraction/data confidence is low — verify key fields before any commitment")
    return flags


# ---------------------------------------------------------------------------
# Strict physical/legal reject screen (confirmed impossibility only)
# ---------------------------------------------------------------------------
def _strict_reject_screen(extracted, economics, gates) -> Optional[str]:
    margin = _f(economics.get("margin"))
    ebitda = _f(economics.get("ebitda"))
    if ebitda is not None and ebitda < 0:
        return "Negative stabilised EBITDA — deal economics do not work"
    if margin is not None and margin < 0:
        return "Negative EBITDA margin — deal economics do not work"
    gba = _f(extracted.get("gba_m2"))
    if gba is not None and 0 < gba < gates.min_viable_gba_m2:
        return f"GBA {gba:.0f} m² is below minimum viable size ({gates.min_viable_gba_m2:.0f} m²)"
    building_type = (extracted.get("building_type") or "").lower()
    if (
        "residential" in building_type and "commercial" not in building_type
        and "mixed" not in building_type and "storage" not in building_type
    ):
        return "Residential-only building — wrong use class for self-storage"
    return None


# ---------------------------------------------------------------------------
# Deterministic hard gates
# ---------------------------------------------------------------------------
def _gate(name, passed, *, actual, threshold, message, severity="review", mandatory=True):
    return {"name": name, "passed": bool(passed), "mandatory": bool(mandatory),
            "severity": severity, "actual": actual, "threshold": threshold, "message": message}


def _evaluate_gates(economics, extracted, gates, *, acquisition_type) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    ebitda = _f(economics.get("ebitda"))
    downside = _f(economics.get("downside_ebitda_eur"))
    margin = _f(economics.get("margin"))
    yld = _f(economics.get("true_ebitda_yield"))
    if yld is None:
        yld = _f(economics.get("ebitda_yield"))
    payback = _f(economics.get("true_payback_years"))
    capex = _f(economics.get("conversion_capex"))
    total_inv = _f(economics.get("total_investment"))

    if acquisition_type == "rent":
        rtr = _f(economics.get("rent_to_revenue_pct"))
        if rtr is not None:
            out.append(_gate("rent_to_revenue", rtr <= gates.rent_hardfail_rent_to_revenue,
                             actual=rtr, threshold=gates.rent_hardfail_rent_to_revenue,
                             message="Rent above 50% of revenue — unsustainable", severity="reject"))
            out.append(_gate("rent_to_revenue_sustainable", rtr <= gates.rent_max_rent_to_revenue,
                             actual=rtr, threshold=gates.rent_max_rent_to_revenue,
                             message="Rent above 35% of revenue — margin pressure"))
        if ebitda is not None:
            out.append(_gate("positive_ebitda", ebitda > gates.rent_min_stabilised_ebitda_eur,
                             actual=ebitda, threshold=gates.rent_min_stabilised_ebitda_eur,
                             message="Stabilised EBITDA not positive after rent", severity="reject"))
        if downside is not None:
            out.append(_gate("downside_ebitda", downside > gates.rent_min_downside_ebitda_eur,
                             actual=downside, threshold=gates.rent_min_downside_ebitda_eur,
                             message="Downside case EBITDA-negative"))
        if margin is not None:
            out.append(_gate("min_margin", margin >= gates.rent_min_ebitda_margin,
                             actual=margin, threshold=gates.rent_min_ebitda_margin,
                             message="EBITDA margin below 15%"))
        if payback is not None:
            out.append(_gate("fitout_payback", payback <= gates.rent_max_fitout_payback_years,
                             actual=payback, threshold=gates.rent_max_fitout_payback_years,
                             message="Payback on invested cash too long for a lease"))
    else:  # buy
        price_per_m2 = _f(economics.get("price_per_m2_eur"))
        if ebitda is not None:
            out.append(_gate("positive_ebitda", ebitda > gates.buy_min_stabilised_ebitda_eur,
                             actual=ebitda, threshold=gates.buy_min_stabilised_ebitda_eur,
                             message="Stabilised EBITDA not positive", severity="reject"))
        if downside is not None:
            out.append(_gate("downside_ebitda", downside > gates.buy_min_downside_ebitda_eur,
                             actual=downside, threshold=gates.buy_min_downside_ebitda_eur,
                             message="Downside case EBITDA-negative"))
        if yld is not None:
            out.append(_gate("true_ebitda_yield", yld >= gates.buy_min_true_ebitda_yield,
                             actual=yld, threshold=gates.buy_min_true_ebitda_yield,
                             message="True EBITDA yield below 8% hurdle"))
        if payback is not None:
            out.append(_gate("payback", payback <= gates.buy_max_payback_years,
                             actual=payback, threshold=gates.buy_max_payback_years,
                             message="Payback exceeds 15 years"))
        if price_per_m2 is not None and price_per_m2 > gates.buy_max_price_per_m2_eur:
            out.append(_gate("affordability_price_per_m2",
                             (yld or 0) >= gates.buy_min_true_ebitda_yield + 0.02,
                             actual={"price_per_m2": price_per_m2, "yield": yld},
                             threshold={"max_price_per_m2": gates.buy_max_price_per_m2_eur},
                             message="Price/m² above market ceiling and yield does not justify it"))

    # Shared.
    if margin is not None:
        out.append(_gate("approval_margin_floor", margin >= gates.min_ebitda_margin_for_approval,
                         actual=margin, threshold=gates.min_ebitda_margin_for_approval,
                         message="EBITDA margin below 20% approval floor"))
    if capex is not None:
        out.append(_gate("capex_included", capex > 0, actual=capex, threshold=0,
                         message="Conversion capex not included"))
    if total_inv is not None:
        out.append(_gate("total_investment_calculated", total_inv > 0, actual=total_inv, threshold=0,
                         message="Total investment not calculated"))
    occ = _f(economics.get("occupancy_rate"))
    if occ is not None:
        out.append(_gate("realistic_occupancy", occ <= gates.max_realistic_stabilised_occupancy,
                         actual=occ, threshold=gates.max_realistic_stabilised_occupancy,
                         message="Assumed stabilised occupancy is unrealistically high"))
    return out


# ---------------------------------------------------------------------------
# Confidence caps
# ---------------------------------------------------------------------------
def _apply_confidence_caps(final, extracted, economics, caps, *, acquisition_type):
    applied: List[Dict[str, Any]] = []

    def cap(reason, value):
        nonlocal final
        if final > value:
            applied.append({"reason": reason, "cap": value})
            final = value

    price_missing = _f(economics.get("asking_price")) in (None, 0)
    rent_missing = _f(economics.get("annual_rent_eur")) in (None, 0)
    if acquisition_type == "buy" and price_missing:
        cap("missing_purchase_price", caps.missing_price_or_rent_max_score)
    if acquisition_type == "rent" and rent_missing:
        cap("missing_rent", caps.missing_price_or_rent_max_score)
    if _f(economics.get("gba_m2")) in (None, 0):
        cap("missing_gba", caps.missing_gba_max_score)
    if _f(economics.get("conversion_capex")) in (None, 0):
        cap("missing_capex_estimate", caps.missing_capex_max_score)
    has_compliance = any(extracted.get(k) is not None and extracted.get(k) != "" for k in
                         ("fire_compliance", "access_type", "loading_access"))
    if not has_compliance:
        cap("missing_access_fire_licensing_evidence", caps.missing_compliance_max_score)
    return final, applied


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def score_property(data: Dict[str, Any], *, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    extracted = data.get("extracted") or {}
    economics = data.get("economics") or {}

    assumptions = merge_overrides(default_assumptions(), overrides)
    gates_cfg = assumptions.gates
    caps_cfg = assumptions.confidence_caps
    thresholds = assumptions.thresholds

    # ----- Category / sub-scores (accept incoming auto_scores) -----------
    incoming = data.get("auto_scores")
    category_scores: Dict[str, int] = {}
    if isinstance(incoming, dict):
        flat = incoming.get("auto_scores") if isinstance(incoming.get("auto_scores"), dict) else incoming
        category_scores = {k: int(v) for k, v in flat.items() if isinstance(v, (int, float))}
    required = set(CATEGORY_WEIGHTS)
    if not required.issubset(category_scores):
        category_scores = calculate_category_scores(extracted, economics)

    base = weighted_base(category_scores)
    confidence = compute_confidence(extracted, economics)

    acquisition_type = (economics.get("acquisition_type") or "").lower()
    if acquisition_type not in ("buy", "rent"):
        acquisition_type = "rent" if _f(economics.get("annual_rent_eur")) else "buy"

    # ----- Confidence caps (ceiling, never additive) ---------------------
    final, score_caps = _apply_confidence_caps(base, extracted, economics, caps_cfg,
                                               acquisition_type=acquisition_type)
    final = _clamp(final)

    # ----- Hard gates ----------------------------------------------------
    gates = _evaluate_gates(economics, extracted, gates_cfg, acquisition_type=acquisition_type)
    gate_failures = [g for g in gates if g["mandatory"] and not g["passed"]]
    reject_failures = [g for g in gate_failures if g["severity"] == "reject"]

    flags = _collect_due_diligence_flags(extracted, economics, confidence)

    # ----- Verdict / deal_status (score band, then gate-gated) -----------
    deal_killer: Optional[str] = None
    reject_reason = _strict_reject_screen(extracted, economics, gates_cfg)

    if final >= thresholds.approved_min:
        deal_status = "approved_candidate"
    elif final >= thresholds.manual_review_min:
        deal_status = "manual_review"
    else:
        deal_status = "rejected"

    if reject_reason:
        deal_status = "rejected"
        deal_killer = reject_reason
    elif reject_failures:
        # Severe economic gate fail — reject unless data confidence is low, in
        # which case a human decides (promote to manual review).
        if confidence["band"] == "low":
            deal_status = "manual_review"
        else:
            deal_status = "rejected"
            deal_killer = reject_failures[0]["message"]
    elif gate_failures and deal_status == "approved_candidate":
        deal_status = "manual_review"

    # Approval also requires confidence + surviving downside.
    approval_blockers: List[str] = []
    if deal_status == "approved_candidate":
        if confidence["pct"] < caps_cfg.min_confidence_pct_for_approval:
            approval_blockers.append("confidence_below_approval_minimum")
        ds = _f(economics.get("downside_ebitda_eur"))
        if ds is not None and ds <= 0:
            approval_blockers.append("downside_ebitda_not_positive")
        if approval_blockers:
            deal_status = "manual_review"

    # Four-tier + legacy verdicts.
    if deal_status == "approved_candidate":
        verdict, verdict_detail, classification = "YES", "APPROVED", "CORE"
    elif deal_status == "rejected":
        verdict, verdict_detail, classification = "NO", "REJECT", "REJECT"
    elif final >= thresholds.approved_min and not reject_failures:
        verdict, verdict_detail, classification = "MANUAL REVIEW", "CONDITIONAL_APPROVAL", "VALUE-ADD"
    else:
        verdict, verdict_detail, classification = "MANUAL REVIEW", "MANUAL_REVIEW", "VALUE-ADD / MANUAL REVIEW"

    conditions = [g["message"] for g in gate_failures] + [
        "Verify data confidence" if "confidence_below_approval_minimum" in approval_blockers else None,
    ]
    conditions = [c for c in conditions if c]

    financial_summary = {
        "acquisition_type": acquisition_type,
        "asking_price_eur": economics.get("asking_price"),
        "annual_rent_eur": economics.get("annual_rent_eur"),
        "gba_m2": economics.get("gba_m2"),
        "nra_m2": economics.get("nra_m2"),
        "price_per_m2_eur": economics.get("price_per_m2_eur"),
        "transaction_costs_eur": economics.get("acquisition_transaction_cost_eur"),
        "total_investment_eur": economics.get("total_investment"),
        "annual_revenue_eur": economics.get("annual_revenue"),
        "ebitda_eur": economics.get("ebitda"),
        "downside_ebitda_eur": economics.get("downside_ebitda_eur"),
        "severe_downside_ebitda_eur": economics.get("severe_downside_ebitda_eur"),
        "ebitda_margin": economics.get("margin"),
        "true_ebitda_yield": economics.get("true_ebitda_yield"),
        "downside_yield_pct": economics.get("downside_yield_pct"),
        "true_payback_years": economics.get("true_payback_years"),
        "rent_to_revenue_pct": economics.get("rent_to_revenue_pct"),
    }

    sub_scores = {
        "financial_return": category_scores.get("financial_return"),
        "operational_feasibility": category_scores.get("operational_feasibility"),
        "location_demand": category_scores.get("location_demand"),
        "physical_suitability": category_scores.get("physical_suitability"),
        "risk": category_scores.get("risk"),
        "data_confidence": confidence["pct"],
    }

    breakdown = {
        "base_score": base,
        "category_scores": category_scores,
        "weights": CATEGORY_WEIGHTS,
        "confidence": confidence,
        "score_caps": score_caps,
        "gates": gates,
        "gate_failures": [g["name"] for g in gate_failures],
        "final_score": final,
        "thresholds": {"approved": thresholds.approved_min, "manual_review": thresholds.manual_review_min},
        "philosophy_version": assumptions.scoring_version,
    }

    return {
        "score": final,
        "verdict": verdict,
        "verdict_detail": verdict_detail,
        "classification": classification,
        "deal_status": deal_status,
        "deal_killer": deal_killer,
        "conditions": conditions,
        "confidence": confidence,
        "scoring_version": assumptions.scoring_version,
        "sub_scores": sub_scores,
        "gates": gates,
        "gate_failures": [g["name"] for g in gate_failures],
        "score_caps": score_caps,
        "financial_summary": financial_summary,
        "due_diligence_flags": flags,
        "auto_scores": category_scores,
        "breakdown": breakdown,
    }
