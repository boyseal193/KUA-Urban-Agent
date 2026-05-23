"""K.U.A. — final scoring orchestrator.

This module sits on top of ``auto_scoring`` (which produces five category
sub-scores) and:

1.  Computes a weighted base score (0–100).
2.  Applies a small number of *capped* adjustments. Cumulative adjustments
    are bounded to ``±MAX_ADJUSTMENT`` so no single quirk can collapse a
    deal.
3.  Applies the **economics floor** — if economics are strong the deal
    cannot drop into rejection over data hygiene issues alone.
4.  Issues due-diligence flags for every uncertain field. Missing data
    produces a flag, NEVER a hard reject.
5.  Runs the strict (rare) **hard-reject** screen for cases that are
    physically or legally impossible. The screen requires *confirmed*
    bad data — uncertain fields never trigger a reject.
6.  Maps the final score onto verdict + classification:

       ≥ 75  → YES         /  CORE
       40–74 → MANUAL REVIEW /  VALUE-ADD / MANUAL REVIEW
       <40   → NO          /  REJECT

Output shape (used by memos, exports, the frontend, and the orchestrator)::

    {
        "score": int,                         # final, clamped 0–100
        "verdict": "YES" | "MANUAL REVIEW" | "NO",
        "classification": str,
        "deal_killer": Optional[str],         # populated only on hard reject
        "due_diligence_flags": List[str],
        "auto_scores": {                      # per-category 0–100
            "economics_score": int,
            "operational_score": int,
            "location_score": int,
            "certainty_score": int,
            "completeness_score": int,
        },
        "breakdown": {
            "base_score": int,
            "positive_adjustments": List[{"name": str, "delta": int}],
            "negative_adjustments": List[{"name": str, "delta": int}],
            "adjustment_total": int,          # clamped sum
            "floor_applied": bool,
            "floor_value": Optional[int],
            "final_score": int,
            "weights": {category: float, ...},
            "philosophy_version": "kua-2.0",
        },
    }
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from auto_scoring import (
    CATEGORY_WEIGHTS,
    calculate_category_scores,
    weighted_base,
)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
MAX_ADJUSTMENT_UP = 10        # cumulative positive cap
MAX_ADJUSTMENT_DOWN = -10     # cumulative negative cap
ECONOMICS_FLOOR_THRESHOLD = 70  # if economics_score ≥ this, floor the total
ECONOMICS_FLOOR_VALUE = 45      # …at this score (top of manual-review band)

THRESHOLD_APPROVED = 75
THRESHOLD_MANUAL = 40

# Hard-reject screen — only ever fires on CONFIRMED catastrophic data.
HARD_REJECT_MIN_GBA = 50        # m² — below this is physically unusable
HARD_REJECT_MIN_MARGIN = 0.0    # margin < 0 → negative EBITDA → kill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clamp(value: float, lo: float = 0, hi: float = 100) -> int:
    return int(round(max(lo, min(hi, value))))


def _floatish(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _hard_reject(reason: str, flags: List[str], breakdown: Dict[str, Any]) -> Dict[str, Any]:
    """Build the standard rejection payload while preserving the breakdown."""
    return {
        "score": 0,
        "verdict": "NO",
        "classification": "REJECT",
        "deal_killer": reason,
        "due_diligence_flags": flags,
        "auto_scores": breakdown.get("category_scores", {}),
        "breakdown": {
            **breakdown,
            "final_score": 0,
            "hard_reject_reason": reason,
        },
    }


# ---------------------------------------------------------------------------
# Adjustment + flag rules
# ---------------------------------------------------------------------------
def _collect_due_diligence_flags(
    extracted: Dict[str, Any],
    economics: Dict[str, Any],
    category_scores: Dict[str, int],
) -> List[str]:
    flags: List[str] = []
    add = flags.append

    if not extracted.get("ceiling_height"):
        add("Ceiling height not confirmed — contact agent before underwriting NRA")
    else:
        try:
            h = float(extracted.get("ceiling_height"))
            if h < 2.4:
                add(f"Ceiling height {h:.2f} m is below 2.4 m — confirm storage conversion is viable")
            elif h < 2.7:
                add(f"Ceiling height {h:.2f} m is tight for storage — verify rack heights and code minimums")
        except Exception:
            add("Ceiling height format unclear — re-extract or confirm with agent")

    if extracted.get("loading_access") is None:
        add("Loading access not confirmed — verify whether van/curbside loading is possible")
    elif extracted.get("loading_access") is False:
        add("Loading access marked unavailable — confirm fallback (curbside / pedestrian-only)")

    floor_level = (extracted.get("floor_level") or "").lower()
    if "basement" in floor_level:
        add("Basement floor — confirm code-compliant access and ventilation")
    if "mezzanine" in floor_level:
        add("Mezzanine layout — verify vertical movement of stored goods is feasible")

    building_type = (extracted.get("building_type") or "").lower()
    if "residential" in building_type and "commercial" not in building_type and "mixed" not in building_type:
        add("Building flagged residential — confirm zoning permits commercial / storage use")

    nra_eff = _floatish(economics.get("nra_efficiency"))
    if nra_eff is not None and nra_eff < 0.70:
        add(f"NRA efficiency {nra_eff:.0%} is below 70% — usable space is thin, reconfirm layout")

    margin = _floatish(economics.get("margin"))
    if margin is not None and 0 <= margin < 0.25:
        add(f"EBITDA margin {margin:.0%} is below 25% — pressure-test OpEx assumptions")

    yld = _floatish(economics.get("true_ebitda_yield")) or _floatish(economics.get("ebitda_yield"))
    if yld is not None and yld < 0.05:
        add(f"True yield {yld:.1%} is below 5% — only proceed if price can move")

    payback = _floatish(economics.get("true_payback_years")) or _floatish(economics.get("payback_years"))
    if payback is not None and payback > 18:
        add(f"Payback {payback:.1f} years is long — re-check acquisition price")

    if category_scores.get("certainty_score", 100) < 50:
        add("Extraction confidence is low — manually verify key fields before any commitment")

    if category_scores.get("completeness_score", 100) < 50:
        add("Listing payload is incomplete — request a full data sheet from the agent")

    return flags


def _collect_adjustments(
    extracted: Dict[str, Any],
    economics: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return ``(positive, negative)`` adjustment lists — small, qualitative.

    These complement the category scores; they handle the qualitative
    "vibes" — premium neighbourhood lift, well-lit description, etc. —
    without ever swinging the final score more than ``MAX_ADJUSTMENT``.
    """
    positives: List[Dict[str, Any]] = []
    negatives: List[Dict[str, Any]] = []

    neighbourhood = (extracted.get("neighbourhood") or "").lower()
    description = (extracted.get("description") or "").lower()
    building_type = (extracted.get("building_type") or "").lower()
    floor_level = (extracted.get("floor_level") or "").lower()
    access_type = (extracted.get("access_type") or "").lower()

    # ----- Positives ----------------------------------------------------
    if any(n in neighbourhood for n in ("eixample", "les corts", "gracia", "gràcia", "fort pienc")):
        positives.append({"name": "premium_neighbourhood", "delta": 3})
    if "new development" in building_type or "new build" in building_type:
        positives.append({"name": "new_development", "delta": 2})
    if "open-plan" in description or "open plan" in description:
        positives.append({"name": "open_plan_layout", "delta": 1})
    if "natural light" in description or "skylight" in description:
        positives.append({"name": "natural_light", "delta": 1})
    ceiling = _floatish(extracted.get("ceiling_height"))
    if ceiling is not None and ceiling >= 3.5:
        positives.append({"name": "tall_ceiling", "delta": 2})

    if extracted.get("loading_access") is True and ("ground" in floor_level or "street" in access_type):
        positives.append({"name": "true_ground_floor_loading", "delta": 2})

    margin = _floatish(economics.get("margin"))
    if margin is not None and margin >= 0.60:
        positives.append({"name": "exceptional_margin", "delta": 2})

    # ----- Negatives — capped cumulatively below -----------------------
    if "raval" in neighbourhood:
        negatives.append({"name": "raval_risk", "delta": -3})
    if "la marina del prat vermell" in neighbourhood:
        negatives.append({"name": "emerging_submarket", "delta": -3})
    if "sant martí de provençals" in neighbourhood:
        negatives.append({"name": "secondary_industrial", "delta": -2})

    if "mezzanine" in floor_level and extracted.get("loading_access") is False:
        negatives.append({"name": "mezzanine_no_loading", "delta": -3})
    if "basement" in floor_level and "ground" not in floor_level and "street" not in floor_level:
        negatives.append({"name": "basement_only", "delta": -3})

    yld = _floatish(economics.get("true_ebitda_yield")) or _floatish(economics.get("ebitda_yield"))
    if yld is not None and yld < 0.04:
        negatives.append({"name": "weak_yield", "delta": -3})

    return positives, negatives


# ---------------------------------------------------------------------------
# Strict reject screen
# ---------------------------------------------------------------------------
def _strict_reject_screen(
    extracted: Dict[str, Any],
    economics: Dict[str, Any],
) -> Optional[str]:
    """Return a string reason iff the deal must be rejected outright.

    Only fires on CONFIRMED catastrophic data. Anything ambiguous → flag.
    """
    margin = _floatish(economics.get("margin"))
    ebitda = _floatish(economics.get("ebitda"))
    if margin is not None and margin < HARD_REJECT_MIN_MARGIN:
        return "Negative EBITDA margin — deal economics do not work"
    if ebitda is not None and ebitda < 0:
        return "Negative EBITDA — deal economics do not work"

    gba = _floatish(extracted.get("gba_m2"))
    if gba is not None and 0 < gba < HARD_REJECT_MIN_GBA:
        return f"GBA {gba:.0f} m² is below minimum viable size ({HARD_REJECT_MIN_GBA} m²)"

    building_type = (extracted.get("building_type") or "").lower()
    if (
        "residential" in building_type
        and "commercial" not in building_type
        and "mixed" not in building_type
        and "storage" not in building_type
    ):
        return "Residential-only building — wrong use class for self-storage conversion"

    # "Truly unusable space" — every signal must agree that this is a no-go.
    floor_level = (extracted.get("floor_level") or "").lower()
    access_type = (extracted.get("access_type") or "").lower()
    nra_eff = _floatish(economics.get("nra_efficiency"))
    if (
        "basement" in floor_level
        and "ground" not in floor_level
        and "street" not in floor_level
        and extracted.get("loading_access") is False
        and not any(k in access_type for k in ("street", "vehicle", "direct", "garage"))
        and nra_eff is not None and nra_eff < 0.60
    ):
        return "Basement-only with no street access, no loading, and unusable NRA — physically infeasible"

    return None


# ---------------------------------------------------------------------------
# Verdict mapping
# ---------------------------------------------------------------------------
def _verdict_for_score(score: int) -> Tuple[str, str]:
    if score >= THRESHOLD_APPROVED:
        return "YES", "CORE"
    if score >= THRESHOLD_MANUAL:
        return "MANUAL REVIEW", "VALUE-ADD / MANUAL REVIEW"
    return "NO", "REJECT"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def score_property(data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the final K.U.A. score for one extracted listing.

    ``data`` follows the existing shape::

        {"extracted": {...}, "economics": {...}, "auto_scores": <optional>}

    If ``auto_scores`` is omitted we compute them on the fly so this function
    is also callable in isolation (e.g. from tests).
    """
    extracted = data.get("extracted") or {}
    economics = data.get("economics") or {}

    # ----- Category scores -------------------------------------------------
    incoming = data.get("auto_scores")
    # Accept either the new nested wrapper or a flat dict.
    if isinstance(incoming, dict):
        flat = incoming.get("auto_scores") or {
            k: incoming.get(k)
            for k in (
                "economics_score",
                "operational_score",
                "location_score",
                "certainty_score",
                "completeness_score",
            )
            if incoming.get(k) is not None
        }
        category_scores = {k: int(v) for k, v in flat.items() if isinstance(v, (int, float))}
    else:
        category_scores = {}

    if not category_scores or set(category_scores) != {
        "economics_score",
        "operational_score",
        "location_score",
        "certainty_score",
        "completeness_score",
    }:
        category_scores = calculate_category_scores(extracted, economics)

    base = weighted_base(category_scores)

    # ----- Adjustments (capped) -------------------------------------------
    positives, negatives = _collect_adjustments(extracted, economics)
    pos_total = sum(int(p["delta"]) for p in positives)
    neg_total = sum(int(n["delta"]) for n in negatives)
    pos_capped = min(pos_total, MAX_ADJUSTMENT_UP)
    neg_capped = max(neg_total, MAX_ADJUSTMENT_DOWN)
    adjustment_total = pos_capped + neg_capped

    final = base + adjustment_total

    # ----- Economics floor -------------------------------------------------
    floor_applied = False
    floor_value: Optional[int] = None
    if category_scores.get("economics_score", 0) >= ECONOMICS_FLOOR_THRESHOLD and final < ECONOMICS_FLOOR_VALUE:
        floor_applied = True
        floor_value = ECONOMICS_FLOOR_VALUE
        final = ECONOMICS_FLOOR_VALUE

    final = _clamp(final)

    # ----- Flags ----------------------------------------------------------
    flags = _collect_due_diligence_flags(extracted, economics, category_scores)

    # ----- Breakdown payload ---------------------------------------------
    breakdown = {
        "base_score": base,
        "category_scores": category_scores,
        "weights": CATEGORY_WEIGHTS,
        "positive_adjustments": positives,
        "negative_adjustments": negatives,
        "positive_total": pos_total,
        "positive_capped_total": pos_capped,
        "negative_total": neg_total,
        "negative_capped_total": neg_capped,
        "adjustment_cap_up": MAX_ADJUSTMENT_UP,
        "adjustment_cap_down": MAX_ADJUSTMENT_DOWN,
        "adjustment_total": adjustment_total,
        "floor_applied": floor_applied,
        "floor_value": floor_value,
        "floor_threshold": ECONOMICS_FLOOR_THRESHOLD,
        "final_score": final,
        "thresholds": {
            "approved": THRESHOLD_APPROVED,
            "manual_review": THRESHOLD_MANUAL,
        },
        "philosophy_version": "kua-2.0",
    }

    # ----- Strict reject screen ------------------------------------------
    reject_reason = _strict_reject_screen(extracted, economics)
    if reject_reason:
        return _hard_reject(reject_reason, flags, breakdown)

    # ----- Verdict --------------------------------------------------------
    verdict, classification = _verdict_for_score(final)

    return {
        "score": final,
        "verdict": verdict,
        "classification": classification,
        "deal_killer": None,
        "due_diligence_flags": flags,
        "auto_scores": category_scores,
        "breakdown": breakdown,
    }
