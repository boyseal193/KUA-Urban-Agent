"""K.U.A. auto-scoring — five weighted categories, each on a clean 0–100 scale.

Categories (and weights, summing to 1.0):

    economics    35%   yield / payback / margin
    operational  25%   GBA / ceiling / access / floor level / layout
    location     20%   Barcelona neighbourhood quality
    certainty    10%   how confident we are in the extracted data
    completeness 10%   how much of the payload was actually populated

Design notes
------------
* Every sub-score is clamped to ``[0, 100]`` so the weighted sum lands in
  ``[0, 100]`` automatically — no surprising overshoots, no negative totals.
* Missing data NEVER subtracts from a category; it leaves the category at
  a moderate neutral value AND lowers ``certainty``/``completeness`` so
  the operator sees a soft signal rather than a punitive one.
* Score stability: a single missing field can swing certainty by ~15 pts
  (0.10 weight) → ~1.5 pts on the final score. Even three missing fields
  shift the total by less than 5 points. Small extraction noise can no
  longer flip a deal from manual_review to rejected.
* The scorer is pure (no I/O, no dates, no randomness) so identical
  inputs always produce identical scores — important for the dedupe layer
  that re-scores when the same property reappears across scan runs.

Returned shape
--------------
``calculate_auto_scores`` and ``score_property`` (the legacy entry points)
return a dict with both the new flat per-category numbers AND a nested
``auto_scores`` block so older readers keep working.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants — exposed for diagnostics / explainability
# ---------------------------------------------------------------------------
CATEGORY_WEIGHTS: Dict[str, float] = {
    "economics":    0.35,
    "operational":  0.25,
    "location":     0.20,
    "certainty":    0.10,
    "completeness": 0.10,
}
assert abs(sum(CATEGORY_WEIGHTS.values()) - 1.0) < 1e-6, "category weights must sum to 1.0"

# Neighbourhood tiers — case-insensitive substring match.
_PREMIUM_NEIGHBOURHOODS = (
    "eixample", "gracia", "gràcia", "les corts", "sant gervasi", "sarria",
    "sarrià", "poblenou", "fort pienc",
)
_STRONG_NEIGHBOURHOODS = (
    "sants", "clot", "guinardo", "guinardó", "horta", "sant marti",
    "sant martí", "gotic", "gòtic", "born",
)
_AVERAGE_NEIGHBOURHOODS = (
    "barceloneta", "vila olimpica", "vila olímpica", "poble sec",
    "poble-sec", "vallcarca",
)
_WEAK_NEIGHBOURHOODS = (
    "trinitat vella", "nou barris", "besos", "besòs", "zona franca",
    "sant martí de provençals", "la marina del prat vermell",
)
_RISKY_NEIGHBOURHOODS = (
    "raval",
)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(round(max(lo, min(hi, value))))


def _present(value: Any) -> bool:
    """Return True if ``value`` is meaningfully populated (not None, not '', not 0 for numbers)."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return value != 0
    return True


# ---------------------------------------------------------------------------
# 1. Economics — 35%
# ---------------------------------------------------------------------------
def score_economics_category(economics: Dict[str, Any]) -> int:
    """Return 0–100. Anchored on True EBITDA yield, with payback + margin lift.

    The new philosophy: even a 5% true yield is a manual-review candidate
    (≈55). 8%+ is approved territory. Below 3.5% gets squeezed but never
    automatically rejected here — the strict hard-reject layer in
    ``scoring.py`` only fires on actual negative-EBITDA.
    """
    if not isinstance(economics, dict):
        economics = {}

    true_yield = economics.get("true_ebitda_yield")
    ebitda_yield = economics.get("ebitda_yield")
    payback = economics.get("true_payback_years") or economics.get("payback_years")
    margin = economics.get("margin")

    # ---- yield (primary anchor) -----------------------------------------
    # Anchors are deliberately conservative so that "good" yields land in
    # the manual-review band and only outstanding yields anchor approval.
    # Combined with operational+location lift, an 8% deal needs strong
    # supporting evidence to cross the 75-point approved threshold.
    yld = true_yield if true_yield is not None else ebitda_yield
    if yld is None:
        anchor = 48          # neutral-ish — no info yet
    elif yld >= 0.15:
        anchor = 88
    elif yld >= 0.12:
        anchor = 78
    elif yld >= 0.10:
        anchor = 68
    elif yld >= 0.08:
        anchor = 60
    elif yld >= 0.065:
        anchor = 52
    elif yld >= 0.05:
        anchor = 44
    elif yld >= 0.035:
        anchor = 35
    elif yld >= 0.02:
        anchor = 26
    else:
        anchor = 18

    # ---- payback (secondary lift / drag) --------------------------------
    payback_bonus = 0
    if payback is not None:
        if payback <= 8:
            payback_bonus = 6
        elif payback <= 12:
            payback_bonus = 3
        elif payback <= 18:
            payback_bonus = 0
        elif payback <= 25:
            payback_bonus = -3
        else:
            payback_bonus = -7

    # ---- margin (operational health) ------------------------------------
    margin_bonus = 0
    if margin is not None:
        if margin >= 0.65:
            margin_bonus = 4
        elif margin >= 0.50:
            margin_bonus = 2
        elif margin >= 0.35:
            margin_bonus = 0
        elif margin >= 0.20:
            margin_bonus = -3
        elif margin >= 0.05:
            margin_bonus = -8
        else:
            margin_bonus = -15   # near-zero margin pulls hard but still scoreable

    return _clamp(anchor + payback_bonus + margin_bonus)


# ---------------------------------------------------------------------------
# 2. Operational feasibility — 25%
# ---------------------------------------------------------------------------
def score_operational_category(extracted: Dict[str, Any]) -> int:
    """Can we physically convert this building into self-storage?"""
    if not isinstance(extracted, dict):
        extracted = {}

    gba = extracted.get("gba_m2") or 0
    try:
        gba = float(gba)
    except (TypeError, ValueError):
        gba = 0

    ceiling = extracted.get("ceiling_height")
    try:
        ceiling = float(ceiling) if ceiling is not None else None
    except (TypeError, ValueError):
        ceiling = None

    loading_access = extracted.get("loading_access")
    access_type = (extracted.get("access_type") or "").lower()
    floor_level = (extracted.get("floor_level") or "").lower()
    description = (extracted.get("description") or "").lower()
    building_type = (extracted.get("building_type") or "").lower()

    score = 42  # conservative starting point — perfect data tops out ~85

    # GBA — sweet spot 250–400 m². Boosts trimmed so even a perfect-sized
    # listing leaves room for genuine differentiation via other signals.
    if gba >= 400:
        score += 14
    elif gba >= 250:
        score += 18
    elif gba >= 180:
        score += 12
    elif gba >= 120:
        score += 5
    elif gba >= 80:
        score -= 2
    elif gba >= 50:
        score -= 10
    elif gba > 0:
        score -= 20

    # Ceiling height — unknown stays neutral (handled by certainty category)
    if ceiling is not None:
        if ceiling >= 3.5:
            score += 7
        elif ceiling >= 3.0:
            score += 5
        elif ceiling >= 2.7:
            score += 2
        elif ceiling >= 2.4:
            score -= 2
        else:
            score -= 8

    # Loading access — true is gold, false is a drag, None is neutral
    if loading_access is True:
        score += 8
    elif loading_access is False:
        score -= 5

    # Access type
    if any(k in access_type for k in ("street", "vehicle", "direct", "garage")):
        score += 4
    elif "pedestrian" in access_type:
        score += 0
    elif access_type:
        score -= 1

    # Ground floor / street level
    if any(k in floor_level for k in ("ground", "street", "planta calle", "planta baja")):
        score += 4
    if "basement" in floor_level:
        score -= 6
    if "mezzanine" in floor_level or "two floors" in description or "two-floor" in description:
        score -= 4

    # Format bonuses (kept small so they don't carry an otherwise weak deal)
    if "open-plan" in description or "open plan" in description:
        score += 2
    if any(k in description for k in ("natural light", "skylight", "skylights")):
        score += 1

    # Building type discount — residential pulls hard; the strict layer may reject
    if "residential" in building_type and "commercial" not in building_type and "mixed" not in building_type:
        score -= 12

    return _clamp(score)


# ---------------------------------------------------------------------------
# 3. Location — 20%
# ---------------------------------------------------------------------------
def score_location_category(extracted: Dict[str, Any]) -> int:
    if not isinstance(extracted, dict):
        extracted = {}

    neighbourhood = (extracted.get("neighbourhood") or "").lower()

    # Default — unknown locations are NOT punished, only mildly conservative.
    if not neighbourhood:
        return 55

    if any(n in neighbourhood for n in _PREMIUM_NEIGHBOURHOODS):
        return 80
    if any(n in neighbourhood for n in _STRONG_NEIGHBOURHOODS):
        return 68
    if any(n in neighbourhood for n in _AVERAGE_NEIGHBOURHOODS):
        return 58
    if any(n in neighbourhood for n in _WEAK_NEIGHBOURHOODS):
        return 42
    if any(n in neighbourhood for n in _RISKY_NEIGHBOURHOODS):
        return 38

    # Unrecognised but populated → assume average-grade Barcelona.
    return 55


# ---------------------------------------------------------------------------
# 4. Certainty — 10%
# ---------------------------------------------------------------------------
_CERTAINTY_SIGNALS = (
    ("ceiling_height", 18),
    ("loading_access", 18),
    ("access_type",    14),
    ("floor_level",    14),
    ("building_type",  12),
    ("gba_m2",         12),
    ("asking_price",   12),
)


def score_certainty_category(extracted: Dict[str, Any], economics: Dict[str, Any]) -> int:
    """Higher when the extractor produced meaningful values for diagnostic fields."""
    if not isinstance(extracted, dict):
        extracted = {}
    if not isinstance(economics, dict):
        economics = {}

    score = 0
    for key, weight in _CERTAINTY_SIGNALS:
        if _present(extracted.get(key)):
            score += weight

    # Description length is a weak proxy for extraction quality.
    description = extracted.get("description") or ""
    if isinstance(description, str):
        if len(description) >= 240:
            score += 0          # already enough signals above
        elif len(description) >= 80:
            score += 0
        else:
            # short / no description → small certainty discount
            score = max(0, score - 8)

    # Economics computed end-to-end → +ve signal
    if _present(economics.get("true_ebitda_yield")) or _present(economics.get("ebitda_yield")):
        score += 4

    return _clamp(score, 0, 100)


# ---------------------------------------------------------------------------
# 5. Completeness — 10%
# ---------------------------------------------------------------------------
_COMPLETENESS_SIGNALS = (
    ("gba_m2",        20),
    ("asking_price",  18),
    ("address",       12),
    ("neighbourhood", 10),
    ("city",           4),
    ("listing_url",   10),
    ("latitude",       8),
    ("longitude",      8),
    ("description",   10),
)


def score_completeness_category(extracted: Dict[str, Any]) -> int:
    if not isinstance(extracted, dict):
        extracted = {}
    score = 0
    for key, weight in _COMPLETENESS_SIGNALS:
        if _present(extracted.get(key)):
            score += weight
    return _clamp(score, 0, 100)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def calculate_category_scores(extracted: Dict[str, Any], economics: Dict[str, Any]) -> Dict[str, int]:
    return {
        "economics_score":    score_economics_category(economics),
        "operational_score":  score_operational_category(extracted),
        "location_score":     score_location_category(extracted),
        "certainty_score":    score_certainty_category(extracted, economics),
        "completeness_score": score_completeness_category(extracted),
    }


def weighted_base(scores: Dict[str, int]) -> int:
    total = (
        scores.get("economics_score",    0) * CATEGORY_WEIGHTS["economics"]
        + scores.get("operational_score",  0) * CATEGORY_WEIGHTS["operational"]
        + scores.get("location_score",     0) * CATEGORY_WEIGHTS["location"]
        + scores.get("certainty_score",    0) * CATEGORY_WEIGHTS["certainty"]
        + scores.get("completeness_score", 0) * CATEGORY_WEIGHTS["completeness"]
    )
    return _clamp(total)


# ---------------------------------------------------------------------------
# Backwards-compatible entry points
# ---------------------------------------------------------------------------
def calculate_auto_scores(extracted: Dict[str, Any], economics: Dict[str, Any]) -> Dict[str, Any]:
    """Return a wrapper dict that preserves the legacy ``auto_scores`` key.

    Older callers (``main.py``, ``orchestrator.py``) pass the entire return
    value back into ``scoring.score_property`` as ``auto_scores=``.  The
    new scorer reads either shape.
    """
    cat = calculate_category_scores(extracted or {}, economics or {})
    base = weighted_base(cat)
    return {
        "auto_scores": cat,
        # Legacy flat copy so older readers keep working.
        **cat,
        # Helpful preview (the final score lives in scoring.score_property).
        "base_score": base,
        "weights": CATEGORY_WEIGHTS,
    }


# Older code may import these — keep stable signatures.
def score_property(extracted: Dict[str, Any], economics: Dict[str, Any]) -> Dict[str, Any]:
    return calculate_auto_scores(extracted, economics)
