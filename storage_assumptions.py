"""Tunable, versioned assumptions for the SELF-STORAGE underwriting engine.

This module is INDEPENDENT of the laundromat model (``laundry/assumptions.py``).
Self-storage economics (occupancy ramp, achieved rent per m², NRA efficiency,
fit-out capex, opex structure) are fundamentally different from a coin-op
laundromat and must never share a formula.

Every constant here is override-able (pass a nested dict to
``merge_overrides``) and is documented in ``ASSUMPTIONS_SOURCES`` with value,
unit, date and citation. Do NOT hardcode market numbers elsewhere.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Tuple


# Bump on any scoring-logic or calibration change. Persisted with each analysis.
SCORING_VERSION = "kua-storage-3.0"


# ---------------------------------------------------------------------------
# Market — achieved storage rent per m² of NRA, per month (Barcelona districts)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DistrictRevenue:
    # EUR per m² of NRA per month. Conservative vs FEDESSA EU avg €296/m²/yr
    # (~€24.7/m²/mo) — Barcelona secondary districts sit below prime.
    table: Dict[str, float] = field(default_factory=lambda: {
        "eixample": 26.0, "gracia": 24.0, "les corts": 25.0, "sant gervasi": 27.0,
        "sarria": 27.0, "poblenou": 22.0, "sants": 21.0, "clot": 21.0,
        "sant marti": 21.0, "horta": 20.0, "guinardo": 20.0, "trinitat vella": 17.0,
        "nou barris": 17.0, "besos": 16.0, "zona franca": 16.0, "raval": 20.0,
        "gotic": 21.0, "born": 22.0,
    })
    default_eur_per_m2_month: float = 20.0


# ---------------------------------------------------------------------------
# Operating model — occupancy ramp, NRA, opex, capex
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OperatingAssumptions:
    # Occupancy — never mature from day one. Mature EU optimum 85–90% (FEDESSA).
    stabilised_occupancy: float = 0.85
    year1_occupancy: float = 0.60          # ~break-even zone in first year
    ramp_months_to_stabilise: float = 24.0  # 18–36 mo typical
    # Downside / severe-downside occupancy for stress cases.
    downside_occupancy: float = 0.72
    severe_downside_occupancy: float = 0.58

    # NRA efficiency (usable/GBA) by GBA band.
    nra_eff_large_min_gba: float = 250.0
    nra_eff_large: float = 0.82
    nra_eff_mid_min_gba: float = 200.0
    nra_eff_mid: float = 0.80
    nra_eff_small: float = 0.78

    avg_unit_size_m2: float = 1.9          # avg let unit incl. corridors already in NRA

    # OpEx — split fixed (per NRA m²/yr) + variable (% of revenue) + property tax.
    # Traditional EU store opex ≈ €120/m²/yr @ ~40–45% EBITDA (Bergen 2026);
    # small urban unmanned conversions modelled conservatively below.
    opex_fixed_eur_per_nra_m2_year: float = 55.0   # staff/tech/insurance/maint/utilities/admin
    opex_variable_pct_of_revenue: float = 0.18     # marketing + bad debt + payment + mgmt fee
    property_tax_pct_of_price: float = 0.011       # Barcelona IBI ~0.66–1.1% of cadastral
    bad_debt_pct_of_revenue: float = 0.03          # included within variable, surfaced for display


@dataclass(frozen=True)
class CapexAssumptions:
    """Conversion fit-out capex, itemised per m² of GBA (buy or rent)."""
    partitions_doors_eur_per_m2: float = 220.0
    lighting_ventilation_eur_per_m2: float = 55.0
    fire_compliance_eur_per_m2: float = 60.0
    access_control_cctv_eur_per_m2: float = 45.0
    flooring_finishes_eur_per_m2: float = 40.0
    reception_signage_eur: float = 12_000.0
    professional_fees_eur: float = 9_000.0
    permits_licence_eur: float = 6_500.0
    contingency_pct: float = 0.10
    working_capital_months: float = 3.0


@dataclass(frozen=True)
class TransactionCosts:
    """Catalonia commercial resale acquisition costs (buy only).

    Progressive ITP from 27 Jun 2025 (Decret llei 5/2025) + notary/registry/legal.
    Identical Spanish tax reality as the laundry module but defined here
    independently so the two verticals never share a code path.
    """
    itp_brackets: Tuple[Tuple[float, float], ...] = (
        (600_000.0, 0.10), (900_000.0, 0.11), (1_500_000.0, 0.12), (float("inf"), 0.13),
    )
    notary_pct: float = 0.004
    registry_pct: float = 0.002
    legal_pct: float = 0.010
    gestoria_eur: float = 500.0


# ---------------------------------------------------------------------------
# Scoring — financial-led weights, thresholds, caps, gates
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScoringWeights:
    """Financial-return-led. A good building/location can no longer, on its
    own, manufacture Approved — financial return dominates and the gates bind.
    Confidence is a CAP, not a weighted addend."""
    financial_return: float = 0.42
    operational_feasibility: float = 0.20
    location_demand: float = 0.14
    physical_suitability: float = 0.14
    risk: float = 0.10


@dataclass(frozen=True)
class ScoringThresholds:
    approved_min: int = 75
    manual_review_min: int = 40


@dataclass(frozen=True)
class ConfidenceCaps:
    missing_price_or_rent_max_score: int = 59
    missing_gba_max_score: int = 59
    missing_capex_max_score: int = 64
    missing_compliance_max_score: int = 69   # access/fire/licensing evidence
    min_confidence_pct_for_approval: float = 60.0


@dataclass(frozen=True)
class UnderwritingGates:
    """Deterministic financial + operational gates. Fail => cannot be Approved.

    Sources: NOI yield-on-cost 8–10% for new EU storage (Shurgard 2025/26,
    Bergen 2026); cap rates 5.5–5.8%; stabilised occupancy 85–90% (FEDESSA).
    """
    # --- BUY -------------------------------------------------------------
    buy_min_stabilised_ebitda_eur: float = 0.0
    buy_min_downside_ebitda_eur: float = 0.0
    buy_min_true_ebitda_yield: float = 0.08     # 8% on total investment
    buy_review_true_ebitda_yield: float = 0.055
    buy_max_payback_years: float = 15.0
    buy_review_max_payback_years: float = 22.0
    buy_max_price_per_m2_eur: float = 6000.0    # Barcelona commercial ceiling

    # --- RENT ------------------------------------------------------------
    rent_max_rent_to_revenue: float = 0.35
    rent_hardfail_rent_to_revenue: float = 0.50
    rent_min_stabilised_ebitda_eur: float = 0.0
    rent_min_downside_ebitda_eur: float = 0.0
    rent_min_ebitda_margin: float = 0.15
    rent_max_fitout_payback_years: float = 6.0

    # --- Shared ----------------------------------------------------------
    min_ebitda_margin_for_approval: float = 0.20   # store-level EBITDA margin
    max_realistic_stabilised_occupancy: float = 0.92  # inputs above => unrealistic
    min_viable_gba_m2: float = 50.0


@dataclass(frozen=True)
class StorageAssumptions:
    district_revenue: DistrictRevenue = field(default_factory=DistrictRevenue)
    operating: OperatingAssumptions = field(default_factory=OperatingAssumptions)
    capex: CapexAssumptions = field(default_factory=CapexAssumptions)
    transaction_costs: TransactionCosts = field(default_factory=TransactionCosts)
    scoring_weights: ScoringWeights = field(default_factory=ScoringWeights)
    thresholds: ScoringThresholds = field(default_factory=ScoringThresholds)
    confidence_caps: ConfidenceCaps = field(default_factory=ConfidenceCaps)
    gates: UnderwritingGates = field(default_factory=UnderwritingGates)
    scoring_version: str = SCORING_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_DEFAULT = StorageAssumptions()


def default_assumptions() -> StorageAssumptions:
    return _DEFAULT


def merge_overrides(base: StorageAssumptions, overrides: Dict[str, Any] | None) -> StorageAssumptions:
    if not overrides:
        return base

    def _merge(dc, patch):
        if not isinstance(patch, dict):
            return dc
        kwargs = {}
        for f in dc.__dataclass_fields__.values():
            current = getattr(dc, f.name)
            if hasattr(current, "__dataclass_fields__"):
                kwargs[f.name] = _merge(current, patch.get(f.name) or {})
            elif f.name in patch:
                try:
                    if isinstance(current, tuple):
                        kwargs[f.name] = tuple(patch[f.name])
                    elif isinstance(current, dict):
                        merged = dict(current)
                        merged.update(patch[f.name] or {})
                        kwargs[f.name] = merged
                    else:
                        kwargs[f.name] = type(current)(patch[f.name])
                except (TypeError, ValueError):
                    kwargs[f.name] = current
            else:
                kwargs[f.name] = current
        return type(dc)(**kwargs)

    return _merge(base, overrides)


def get_storage_revenue(neighbourhood: str, assumptions: StorageAssumptions | None = None) -> float:
    a = assumptions or _DEFAULT
    if not neighbourhood:
        return a.district_revenue.default_eur_per_m2_month
    n = neighbourhood.lower()
    for district, price in a.district_revenue.table.items():
        if district in n:
            return price
    return a.district_revenue.default_eur_per_m2_month


ASSUMPTIONS_SOURCES: Dict[str, Dict[str, str]] = {
    "storage_stabilised_occupancy": {
        "value": "85–90% mature; EU avg ~78.7%", "unit": "% occupancy", "date": "2024/2026",
        "source": "FEDESSA European Industry Report 2024; Shurgard Annual Report 2025",
        "note": "Stabilised set to 85%; never assume mature occupancy from day one.",
    },
    "storage_leaseup_ramp": {
        "value": "18–36 months to 85%; break-even 55–65%", "unit": "months / % occ",
        "date": "2025/2026", "source": "The Storage Brief; DealForge; Donald Jones Consulting",
        "note": "Year-1 occupancy modelled at 60%; ramp 24 months base.",
    },
    "storage_noi_yield_on_cost": {
        "value": "8–10% target new development; cap rates 5.5–5.8%", "unit": "% yield",
        "date": "2025/2026", "source": "Shurgard Annual Report 2025; Bergen Research 2026",
        "note": "Approval true-yield hurdle 8%; review floor 5.5%.",
    },
    "storage_ebitda_margin": {
        "value": "40–45% traditional; 60–67% unmanned; NOI 65–75% institutional",
        "unit": "% EBITDA/NOI margin", "date": "2026", "source": "Bergen Research 2026; Shurgard 2025",
        "note": "Approval store-level EBITDA margin floor 20% (conservative for small urban).",
    },
    "storage_revenue_per_m2": {
        "value": "EU avg €296/m²/yr (~€24.7/m²/mo)", "unit": "EUR/m² NRA/year",
        "date": "2024", "source": "FEDESSA European Industry Report 2024",
        "note": "Barcelona district table 16–27 €/m²/mo sits at/below EU avg.",
    },
    "itp_catalonia_progressive": {
        "value": "10/11/12/13% progressive", "unit": "% of price", "date": "2026 (Decret llei 5/2025)",
        "source": "camiacasa.cat, casaconnecta.com", "note": "Resale transfer tax + ~1.6% fees.",
    },
}
