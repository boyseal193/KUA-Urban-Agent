"""Underwriting-calibration tests for the SELF-STORAGE engine (v3).

Independent of the laundromat tests. Verifies financial-return-led weighting,
confidence caps, deterministic hard gates, and gated verdicts.

Run: python3 -m pytest tests/test_storage_underwriting.py -q
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import economics as econ
import scoring


def _score(extracted, *, overrides=None):
    e = econ.calculate_economics(dict(extracted), overrides=overrides)
    r = scoring.score_property({"extracted": extracted, "economics": e}, overrides=overrides)
    return r, e


STRONG_LOC = {"neighbourhood": "Eixample", "city": "Barcelona",
              "ceiling_height": 3.2, "loading_access": True, "access_type": "street",
              "floor_level": "ground", "building_type": "commercial", "fire_compliance": True}


def test_expensive_buy_weak_returns_not_approved():
    r, e = _score({**STRONG_LOC, "acquisition_type": "buy", "asking_price": 900_000, "gba_m2": 250})
    assert e["acquisition_transaction_cost_eur"] > 0
    assert e["total_investment"] > e["asking_price"]
    assert r["deal_status"] != "approved_candidate"
    assert "true_ebitda_yield" in r["gate_failures"] or "payback" in r["gate_failures"]


def test_transaction_costs_and_downside_present():
    r, e = _score({**STRONG_LOC, "acquisition_type": "buy", "asking_price": 500_000, "gba_m2": 300})
    assert e["price_per_m2_eur"] is not None
    assert e["downside_ebitda_eur"] is not None
    assert e["severe_downside_ebitda_eur"] is not None
    assert e["capex_breakdown"]  # itemised capex
    assert r["scoring_version"].startswith("kua-storage")


def test_negative_ebitda_rent_rejected():
    # Huge rent -> negative EBITDA -> severe gate -> reject (data confidence is high).
    r, e = _score({**STRONG_LOC, "acquisition_type": "rent", "asking_rent_month": 30_000, "gba_m2": 200})
    assert e["ebitda"] <= 0
    assert r["deal_status"] == "rejected"
    assert "positive_ebitda" in r["gate_failures"]


def test_strong_location_poor_economics_not_approved():
    r, _ = _score({**STRONG_LOC, "acquisition_type": "buy", "asking_price": 2_000_000, "gba_m2": 200})
    assert r["deal_status"] != "approved_candidate"
    assert r["verdict_detail"] in ("MANUAL_REVIEW", "CONDITIONAL_APPROVAL", "REJECT")


def test_missing_gba_confidence_cap():
    r, _ = _score({"acquisition_type": "buy", "asking_price": 300_000, "neighbourhood": "Eixample"})
    assert r["score"] <= 59
    assert r["deal_status"] != "approved_candidate"


def test_missing_price_confidence_cap():
    r, _ = _score({"acquisition_type": "buy", "gba_m2": 250, "neighbourhood": "Eixample",
                   "ceiling_height": 3.0, "access_type": "street", "fire_compliance": True})
    assert r["score"] <= 59  # missing purchase price


def test_missing_compliance_cap():
    # Everything present except access/fire/licensing evidence.
    r, _ = _score({"acquisition_type": "buy", "asking_price": 250_000, "gba_m2": 300,
                   "neighbourhood": "Eixample", "ceiling_height": 3.2})
    caps = [c["reason"] for c in r["score_caps"]]
    assert "missing_access_fire_licensing_evidence" in caps
    assert r["score"] <= 69


def test_realistic_occupancy_not_from_day_one():
    _, e = econ.calculate_economics({"acquisition_type": "buy", "asking_price": 400_000, "gba_m2": 300}), None
    e = econ.calculate_economics({"acquisition_type": "buy", "asking_price": 400_000, "gba_m2": 300})
    assert e["occupancy_rate"] <= 0.90
    assert e["year1_occupancy"] < e["stabilised_occupancy"]


def test_cheap_high_yield_can_qualify():
    # Very cheap freehold with strong storage revenue -> should pass positive/yield gates.
    r, e = _score({**STRONG_LOC, "acquisition_type": "buy", "asking_price": 120_000, "gba_m2": 300})
    assert "positive_ebitda" not in r["gate_failures"]
    assert r["verdict_detail"] in ("APPROVED", "CONDITIONAL_APPROVAL", "MANUAL_REVIEW")


def test_progressive_itp_brackets():
    from storage_assumptions import default_assumptions
    tx = default_assumptions().transaction_costs
    costs = econ._acquisition_transaction_costs(1_000_000, tx)
    assert abs(costs["itp_eur"] - 105_000) < 1.0  # 60k+33k+12k


def test_legacy_keys_preserved():
    r, e = _score({**STRONG_LOC, "acquisition_type": "buy", "asking_price": 400_000, "gba_m2": 250})
    for k in ("score", "verdict", "classification", "deal_killer", "due_diligence_flags",
              "auto_scores", "breakdown"):
        assert k in r
    for k in ("model_type", "nra_efficiency", "true_ebitda_yield", "conversion_capex",
              "total_investment", "margin", "ebitda"):
        assert k in e
    for k in ("economics_score", "operational_score", "location_score",
              "certainty_score", "completeness_score"):
        assert k in r["auto_scores"]
