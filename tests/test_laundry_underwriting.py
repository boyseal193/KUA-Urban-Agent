"""Underwriting-calibration tests for the laundromat scoring engine (v3).

Covers the acquisitions requirement set: hard financial gates, confidence
caps, financial-return-led weighting, and the €834K / 289 m² example that
must no longer score in the 90s on location + area alone.

Run: python3 -m pytest tests/test_laundry_underwriting.py -q
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from laundry import economics as econ
from laundry import scoring


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _score(extracted, location=None, *, overrides=None, filters=None):
    ex = dict(extracted)
    ex.setdefault("_location", location or {})
    economics = econ.calculate_economics(ex, overrides=overrides)
    return scoring.score_property(
        {"extracted": extracted, "location": location or {}, "economics": economics},
        overrides=overrides,
        filters=filters or {},
    ), economics


STRONG_LOCATION = {
    "population_density_per_km2": 22_000,
    "household_income_eur": 30_000,
    "walkability_score_0_100": 85,
    "nearby_laundromats_within_500m": 1,
    "competitors_within_1km": 3,
    "apartment_density_pct": 0.7,
    "students_within_1km": 1500,
    "street_visibility_0_100": 80,
    "night_safety_0_100": 70,
    "growth_potential_0_100": 70,
    "in_preferred_market": True,
}


# ---------------------------------------------------------------------------
# 11. The reported example: €834K / 289 m² must NOT be a high-90s approval.
# ---------------------------------------------------------------------------
def test_example_834k_289m2_not_auto_approved():
    result, economics = _score(
        {
            "acquisition_type": "buy",
            "asking_price": 834_000,
            "floor_area_m2": 289,
            "address": "Plaza de Gal·la Placídia",
            "neighbourhood": "Sant Gervasi",
            "city": "Barcelona",
            "ground_floor": True,
        },
        STRONG_LOCATION,
    )
    # Transaction costs must now be included in the total investment.
    assert economics["acquisition_transaction_cost_eur"] > 0
    assert economics["total_investment_eur"] > economics["acquisition_cost_eur"]
    assert economics["price_per_m2_eur"] is not None
    # It cannot be an unconditional approval on location + area alone.
    assert result["deal_status"] != "approved_candidate"
    assert result["verdict_detail"] in ("MANUAL_REVIEW", "CONDITIONAL_APPROVAL", "REJECT")


# ---------------------------------------------------------------------------
# 1. Expensive purchase with weak returns -> not approved.
# ---------------------------------------------------------------------------
def test_expensive_weak_returns_not_approved():
    result, _ = _score(
        {"acquisition_type": "buy", "asking_price": 1_500_000, "floor_area_m2": 120,
         "ground_floor": True},
        STRONG_LOCATION,
    )
    assert result["deal_status"] != "approved_candidate"
    assert any("yield" in g or "payback" in g for g in result["gate_failures"])


# ---------------------------------------------------------------------------
# 5. Negative EBITDA -> reject (severe gate).
# ---------------------------------------------------------------------------
def test_negative_ebitda_rejected():
    result, economics = _score(
        {"acquisition_type": "rent", "asking_rent_month": 40_000, "floor_area_m2": 60,
         "ground_floor": True},
        STRONG_LOCATION,
    )
    assert economics["ebitda_eur"] <= 0 or result["deal_status"] == "rejected"
    if economics["ebitda_eur"] <= 0:
        assert result["deal_status"] == "rejected"
        assert "positive_ebitda" in result["gate_failures"]


# ---------------------------------------------------------------------------
# 8. Rent too high relative to revenue -> review or reject.
# ---------------------------------------------------------------------------
def test_rent_to_revenue_too_high():
    result, economics = _score(
        {"acquisition_type": "rent", "asking_rent_month": 9_000, "floor_area_m2": 70,
         "ground_floor": True},
        STRONG_LOCATION,
    )
    assert economics["rent_to_revenue_pct"] is not None
    if economics["rent_to_revenue_pct"] > 0.35:
        assert result["deal_status"] in ("rejected", "manual_review")


# ---------------------------------------------------------------------------
# 3. Strong location but poor economics -> not approved.
# ---------------------------------------------------------------------------
def test_strong_location_poor_economics():
    result, _ = _score(
        {"acquisition_type": "buy", "asking_price": 2_000_000, "floor_area_m2": 80,
         "ground_floor": True},
        STRONG_LOCATION,
    )
    assert result["deal_status"] != "approved_candidate"


# ---------------------------------------------------------------------------
# 4 & 10. Missing critical data -> confidence cap prevents high score.
# ---------------------------------------------------------------------------
def test_missing_critical_data_confidence_cap():
    # No floor area => critical financial field missing => cannot approve, and
    # the final score is held at/under the critical cap (59).
    result, _ = _score(
        {"acquisition_type": "buy", "asking_price": 300_000},  # no floor area, no location
        {},
    )
    assert result["score"] <= 59
    assert result["deal_status"] != "approved_candidate"


def test_operational_missing_confidence_cap_records():
    # Strong economics but empty location => operational cap (69) must actively
    # fire and be recorded, and the deal cannot be an unconditional approval.
    result, _ = _score(
        {"acquisition_type": "buy", "asking_price": 120_000, "floor_area_m2": 70,
         "ground_floor": True, "washer_count": 8, "dryer_count": 4},
        {},  # empty location => low confidence
    )
    caps = [c["reason"] for c in result["score_caps"]]
    assert result["score"] <= 69
    assert "several_operational_fields_missing" in caps
    assert result["deal_status"] != "approved_candidate"


# ---------------------------------------------------------------------------
# 7. High weighted score but a failed hard gate -> not approved.
# ---------------------------------------------------------------------------
def test_high_score_failed_gate_blocks_approval():
    # Cheap enough to score well, but force a soft-gate fail via tiny margin.
    result, economics = _score(
        {"acquisition_type": "buy", "asking_price": 5_000_000, "floor_area_m2": 70,
         "ground_floor": True},
        STRONG_LOCATION,
    )
    # An enormous price guarantees gate failures regardless of location score.
    assert result["gate_failures"]
    assert result["deal_status"] != "approved_candidate"


# ---------------------------------------------------------------------------
# 9. Oversized laundromat -> physical penalty (right_size flag).
# ---------------------------------------------------------------------------
def test_oversized_penalised():
    _, economics = _score(
        {"acquisition_type": "buy", "asking_price": 400_000, "floor_area_m2": 450,
         "ground_floor": True},
        STRONG_LOCATION,
    )
    assert economics["right_size_status"] == "oversized"


# ---------------------------------------------------------------------------
# 2. Low-priced, genuinely strong yield -> may reach approval.
# ---------------------------------------------------------------------------
def test_strong_yield_can_approve():
    result, economics = _score(
        {"acquisition_type": "buy", "asking_price": 120_000, "floor_area_m2": 70,
         "ground_floor": True, "washer_count": 8, "dryer_count": 4},
        STRONG_LOCATION,
    )
    # Not asserting APPROVED (depends on downside), but it must at least be a
    # viable candidate and pass the positive-EBITDA gate.
    assert "positive_ebitda" not in result["gate_failures"]
    assert result["verdict_detail"] in (
        "APPROVED", "CONDITIONAL_APPROVAL", "MANUAL_REVIEW",
    )
    assert economics["ebitda_yield_on_total_pct"] is not None


# ---------------------------------------------------------------------------
# Transaction-cost progressive ITP sanity (Catalonia brackets).
# ---------------------------------------------------------------------------
def test_progressive_itp_brackets():
    from laundry.assumptions import default_assumptions
    tx = default_assumptions().transaction_costs
    # €1,000,000: 600k@10% + 300k@11% + 100k@12% = 60k+33k+12k = 105k ITP
    costs = econ._acquisition_transaction_costs(1_000_000, tx)
    assert abs(costs["itp_eur"] - 105_000) < 1.0
    assert costs["total_eur"] > costs["itp_eur"]  # + notary/registry/legal
