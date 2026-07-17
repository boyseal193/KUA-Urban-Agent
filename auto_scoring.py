"""K.U.A. self-storage category sub-scores (v3 — financial-return-led).

Six independent dimensions:

    financial_return         42%   true EBITDA yield / payback / margin / downside
    operational_feasibility  20%   NRA efficiency / unit granularity / access
    location_demand          14%   Barcelona storage-demand tiers
    physical_suitability     14%   GBA / ceiling / floor / building type
    risk                     10%   change-of-use / fire / access / flood
    data_confidence          (CAP, not additive) — held out of the weighted base

Design rules enforced here:
* Financial return carries the largest weight; a strong building/location can
  no longer offset weak economics.
* Missing/unknown data NEVER earns positive points — it lowers confidence,
  which caps the final score in ``scoring.py`` (confidence is a ceiling).
* Legacy keys (``economics_score``/``operational_score``/``location_score``/
  ``certainty_score``/``completeness_score``) are still emitted so existing
  exports and the frontend keep working.
"""
from __future__ import annotations

from typing import Any, Dict


# Weighted base is over the five INVESTMENT dimensions only. Confidence is a cap.
CATEGORY_WEIGHTS: Dict[str, float] = {
    "financial_return":        0.42,
    "operational_feasibility": 0.20,
    "location_demand":         0.14,
    "physical_suitability":    0.14,
    "risk":                    0.10,
}
assert abs(sum(CATEGORY_WEIGHTS.values()) - 1.0) < 1e-6

_PREMIUM_NEIGHBOURHOODS = (
    "eixample", "gracia", "gràcia", "les corts", "sant gervasi", "sarria",
    "sarrià", "poblenou", "fort pienc",
)
_STRONG_NEIGHBOURHOODS = (
    "sants", "clot", "guinardo", "guinardó", "horta", "sant marti", "sant martí",
    "gotic", "gòtic", "born",
)
_AVERAGE_NEIGHBOURHOODS = (
    "barceloneta", "vila olimpica", "vila olímpica", "poble sec", "poble-sec", "vallcarca",
)
_WEAK_NEIGHBOURHOODS = (
    "trinitat vella", "nou barris", "besos", "besòs", "zona franca",
    "sant martí de provençals", "la marina del prat vermell",
)
_RISKY_NEIGHBOURHOODS = ("raval",)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(round(max(lo, min(hi, value))))


def _f(value: Any):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return value != 0
    return True


# ---------------------------------------------------------------------------
# 1. Financial return (42%) — the dominant dimension
# ---------------------------------------------------------------------------
def score_financial_return(economics: Dict[str, Any]) -> int:
    if not isinstance(economics, dict):
        economics = {}
    ebitda = _f(economics.get("ebitda"))
    yld = economics.get("true_ebitda_yield")
    if yld is None:
        yld = economics.get("ebitda_yield")
    yld = _f(yld)
    payback = _f(economics.get("true_payback_years")) or _f(economics.get("payback_years"))
    margin = _f(economics.get("margin"))
    downside = _f(economics.get("downside_ebitda_eur"))

    if ebitda is not None and ebitda <= 0:
        return 10
    if yld is None:
        return 40  # no economics computed yet -> neutral-low, confidence will cap

    if yld >= 0.10:
        anchor = 88.0
    elif yld >= 0.08:
        anchor = 72.0
    elif yld >= 0.065:
        anchor = 58.0
    elif yld >= 0.055:
        anchor = 48.0
    elif yld >= 0.045:
        anchor = 38.0
    elif yld >= 0.03:
        anchor = 28.0
    else:
        anchor = 15.0

    if payback is not None:
        if payback <= 10:
            anchor += 8
        elif payback <= 15:
            anchor += 2
        elif payback <= 20:
            anchor += 0
        elif payback <= 28:
            anchor -= 8
        else:
            anchor -= 14

    if margin is not None:
        if margin >= 0.55:
            anchor += 4
        elif margin >= 0.40:
            anchor += 2
        elif margin >= 0.25:
            anchor += 0
        elif margin >= 0.15:
            anchor -= 4
        else:
            anchor -= 12

    if downside is not None and downside <= 0:
        anchor -= 12

    return _clamp(anchor)


# ---------------------------------------------------------------------------
# 2. Operational feasibility (20%)
# ---------------------------------------------------------------------------
def score_operational_feasibility(extracted: Dict[str, Any], economics: Dict[str, Any]) -> int:
    if not isinstance(extracted, dict):
        extracted = {}
    if not isinstance(economics, dict):
        economics = {}
    score = 45.0

    nra_eff = _f(economics.get("nra_efficiency"))
    if nra_eff is not None:
        if nra_eff >= 0.82:
            score += 8
        elif nra_eff >= 0.80:
            score += 5
        elif nra_eff >= 0.78:
            score += 2

    units = _f(economics.get("estimated_units")) or 0
    if units >= 60:
        score += 10
    elif units >= 30:
        score += 6
    elif units >= 15:
        score += 2
    elif units > 0:
        score -= 4

    loading = extracted.get("loading_access")
    if loading is True:
        score += 6
    elif loading is False:
        score -= 5

    access_type = (extracted.get("access_type") or "").lower()
    if any(k in access_type for k in ("street", "vehicle", "direct", "garage")):
        score += 4

    return _clamp(score)


# ---------------------------------------------------------------------------
# 3. Location & demand (14%) — unknown is NOT rewarded
# ---------------------------------------------------------------------------
def score_location_demand(extracted: Dict[str, Any]) -> int:
    if not isinstance(extracted, dict):
        extracted = {}
    neighbourhood = (extracted.get("neighbourhood") or "").lower()
    if not neighbourhood:
        return 45  # unknown -> conservative, below the manual-review midpoint
    if any(n in neighbourhood for n in _PREMIUM_NEIGHBOURHOODS):
        return 78
    if any(n in neighbourhood for n in _STRONG_NEIGHBOURHOODS):
        return 65
    if any(n in neighbourhood for n in _AVERAGE_NEIGHBOURHOODS):
        return 55
    if any(n in neighbourhood for n in _WEAK_NEIGHBOURHOODS):
        return 40
    if any(n in neighbourhood for n in _RISKY_NEIGHBOURHOODS):
        return 35
    return 50


# ---------------------------------------------------------------------------
# 4. Physical suitability (14%)
# ---------------------------------------------------------------------------
def score_physical_suitability(extracted: Dict[str, Any]) -> int:
    if not isinstance(extracted, dict):
        extracted = {}
    gba = _f(extracted.get("gba_m2")) or 0
    ceiling = _f(extracted.get("ceiling_height"))
    floor_level = (extracted.get("floor_level") or "").lower()
    building_type = (extracted.get("building_type") or "").lower()
    description = (extracted.get("description") or "").lower()

    score = 42.0
    if gba >= 400:
        score += 12
    elif gba >= 250:
        score += 16
    elif gba >= 180:
        score += 10
    elif gba >= 120:
        score += 4
    elif gba >= 80:
        score -= 2
    elif gba >= 50:
        score -= 10
    elif gba > 0:
        score -= 20

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

    if any(k in floor_level for k in ("ground", "street", "planta calle", "planta baja")):
        score += 4
    if "basement" in floor_level:
        score -= 6
    if "mezzanine" in floor_level or "two floors" in description:
        score -= 4
    if "residential" in building_type and "commercial" not in building_type and "mixed" not in building_type:
        score -= 12

    return _clamp(score)


# ---------------------------------------------------------------------------
# 5. Risk (10%)
# ---------------------------------------------------------------------------
def score_risk(extracted: Dict[str, Any], economics: Dict[str, Any]) -> int:
    if not isinstance(extracted, dict):
        extracted = {}
    score = 75.0
    floor_level = (extracted.get("floor_level") or "").lower()
    building_type = (extracted.get("building_type") or "").lower()

    if extracted.get("requires_change_of_use"):
        score -= 12
    if extracted.get("fire_compliance") is False or extracted.get("fire_risk_flag"):
        score -= 15
    if extracted.get("loading_access") is False:
        score -= 8
    if "basement" in floor_level and "ground" not in floor_level and "street" not in floor_level:
        score -= 8
    if extracted.get("flood_risk_flag"):
        score -= 10
    if "residential" in building_type and "commercial" not in building_type and "mixed" not in building_type:
        score -= 10
    return _clamp(score)


# ---------------------------------------------------------------------------
# Confidence signals (held OUT of the weighted base — used as a cap)
# ---------------------------------------------------------------------------
_CERTAINTY_SIGNALS = (
    ("ceiling_height", 18), ("loading_access", 18), ("access_type", 14),
    ("floor_level", 14), ("building_type", 12), ("gba_m2", 12), ("asking_price", 12),
)
_COMPLETENESS_SIGNALS = (
    ("gba_m2", 20), ("asking_price", 18), ("address", 12), ("neighbourhood", 10),
    ("city", 4), ("listing_url", 10), ("latitude", 8), ("longitude", 8), ("description", 10),
)


def score_certainty_category(extracted: Dict[str, Any], economics: Dict[str, Any]) -> int:
    extracted = extracted if isinstance(extracted, dict) else {}
    economics = economics if isinstance(economics, dict) else {}
    score = sum(w for k, w in _CERTAINTY_SIGNALS if _present(extracted.get(k)))
    if _present(economics.get("true_ebitda_yield")) or _present(economics.get("ebitda_yield")):
        score += 4
    return _clamp(score)


def score_completeness_category(extracted: Dict[str, Any]) -> int:
    extracted = extracted if isinstance(extracted, dict) else {}
    return _clamp(sum(w for k, w in _COMPLETENESS_SIGNALS if _present(extracted.get(k))))


def compute_confidence(extracted: Dict[str, Any], economics: Dict[str, Any]) -> Dict[str, Any]:
    certainty = score_certainty_category(extracted, economics)
    completeness = score_completeness_category(extracted)
    pct = round(certainty * 0.6 + completeness * 0.4, 1)
    band = "high" if pct >= 70 else ("low" if pct < 45 else "medium")
    return {"pct": pct, "band": band, "certainty": certainty, "completeness": completeness}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def calculate_category_scores(extracted: Dict[str, Any], economics: Dict[str, Any]) -> Dict[str, int]:
    fin = score_financial_return(economics)
    ope = score_operational_feasibility(extracted, economics)
    loc = score_location_demand(extracted)
    phys = score_physical_suitability(extracted)
    risk = score_risk(extracted, economics)
    conf = compute_confidence(extracted, economics)
    return {
        # new six-dimension view
        "financial_return": fin,
        "operational_feasibility": ope,
        "location_demand": loc,
        "physical_suitability": phys,
        "risk": risk,
        "data_confidence": int(round(conf["pct"])),
        # legacy aliases (exports / frontend)
        "economics_score": fin,
        "operational_score": ope,
        "location_score": loc,
        "certainty_score": conf["certainty"],
        "completeness_score": conf["completeness"],
    }


def weighted_base(scores: Dict[str, int]) -> int:
    total = sum(scores.get(k, 0) * w for k, w in CATEGORY_WEIGHTS.items())
    return _clamp(total)


def calculate_auto_scores(extracted: Dict[str, Any], economics: Dict[str, Any]) -> Dict[str, Any]:
    cat = calculate_category_scores(extracted or {}, economics or {})
    base = weighted_base(cat)
    return {
        "auto_scores": cat,
        **cat,
        "base_score": base,
        "weights": CATEGORY_WEIGHTS,
    }


def score_property(extracted: Dict[str, Any], economics: Dict[str, Any]) -> Dict[str, Any]:
    return calculate_auto_scores(extracted, economics)
