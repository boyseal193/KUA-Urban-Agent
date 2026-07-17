"""Tunable defaults for the laundromat underwriting engine.

Every constant here can be overridden at runtime by a JSON blob passed via
``POST /laundry/scans`` (``overrides`` / ``scoring_overrides`` / ``filters``)
or persisted to the `laundry_settings` Supabase table.

Target operator profile
-----------------------

Small, dense, urban laundromats:
* 60 – 80 m² (ideal 70 m²)
* ~10 machines (configurable washer / dryer / large / stacking mix)
* Preferred Barcelona markets: Raval, Sant Antoni, Poble Sec, Clot, Hospitalet
* Renter-heavy / small-housing / mid-income demographics
* Room for ancillary revenue (Amazon/InPost lockers, vending, drop-off)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Tuple


# ---------------------------------------------------------------------------
# Machine fleet
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MachineMix:
    target_washers: int = 7
    target_dryers: int = 3
    target_large_washers: int = 2
    target_small_washers: int = 5
    target_stacking_dryers: int = 2
    folding_stations: int = 2
    seating_units: int = 6
    detergent_vending: int = 1
    snack_vending: int = 1
    drink_vending: int = 0
    payment_kiosks: int = 1


@dataclass(frozen=True)
class MachineAssumptions:
    washer_unit_capex_eur: float = 7_500.0
    large_washer_unit_capex_eur: float = 10_500.0
    dryer_unit_capex_eur: float = 5_000.0
    stacking_dryer_unit_capex_eur: float = 7_200.0
    soap_vending_capex_eur: float = 2_400.0
    snack_vending_capex_eur: float = 3_500.0
    drink_vending_capex_eur: float = 3_200.0
    payment_kiosk_capex_eur: float = 4_800.0
    folding_table_capex_eur: float = 350.0
    seating_unit_capex_eur: float = 180.0

    washer_footprint_m2: float = 2.5
    dryer_footprint_m2: float = 2.5
    stacking_dryer_footprint_m2: float = 1.6
    aisle_seating_ratio: float = 0.45

    avg_cycles_per_washer_day: float = 4.5
    avg_cycles_per_large_washer_day: float = 3.8
    avg_cycles_per_dryer_day: float = 4.0
    avg_revenue_per_wash_cycle_eur: float = 5.50
    avg_revenue_per_large_wash_cycle_eur: float = 8.50
    avg_revenue_per_dry_cycle_eur: float = 3.50

    water_litres_per_wash: float = 60.0
    water_litres_per_large_wash: float = 95.0
    electricity_kwh_per_wash: float = 0.75
    electricity_kwh_per_dry: float = 3.20
    gas_kwh_per_dry: float = 4.50


@dataclass(frozen=True)
class SecondaryRevenue:
    amazon_locker_eur_year: float = 4_800.0
    inpost_locker_eur_year: float = 3_600.0
    detergent_vending_eur_year: float = 2_400.0
    snack_vending_eur_year: float = 2_900.0
    drink_vending_eur_year: float = 2_600.0
    atm_eur_year: float = 1_800.0
    advertising_eur_year: float = 1_500.0
    drop_off_service_eur_year: float = 9_500.0
    commercial_contract_eur_year: float = 14_000.0
    dry_cleaning_partner_eur_year: float = 2_400.0


@dataclass(frozen=True)
class FitOutAssumptions:
    fit_out_eur_per_m2: float = 650.0
    electrical_upgrade_eur_per_m2: float = 95.0
    plumbing_upgrade_eur_per_m2: float = 70.0
    ventilation_eur_per_m2: float = 55.0
    drainage_upgrade_eur_per_m2: float = 40.0

    gas_connection_eur: float = 6_500.0
    water_supply_upgrade_eur: float = 3_200.0
    signage_branding_eur: float = 4_800.0
    legal_costs_eur: float = 3_500.0
    licensing_permits_eur: float = 2_200.0
    initial_marketing_eur: float = 3_000.0
    working_capital_months: float = 3.0


@dataclass(frozen=True)
class OpexAssumptions:
    base_electricity_eur_per_m2_year: float = 14.0
    base_water_eur_per_m2_year: float = 4.0

    electricity_eur_per_kwh: float = 0.21
    gas_eur_per_kwh: float = 0.085
    water_eur_per_m3: float = 2.65

    insurance_eur_per_year: float = 1_650.0
    internet_eur_per_year: float = 480.0
    waste_eur_per_year: float = 720.0
    cleaning_eur_per_m2_year: float = 22.0
    supplies_eur_per_m2_year: float = 11.0
    maintenance_pct_of_revenue: float = 0.05

    monthly_part_time_attendant_eur: float = 720.0
    monthly_remote_manager_eur: float = 280.0


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScoringWeights:
    """Financial-return-led weighting (v3 recalibration).

    Rationale: the previous split (economics 0.28, location 0.30) let a strong
    location/physical grade carry a financially weak deal to Approved. The
    acquisitions mandate is that *financial return* dominates. Economics now
    leads at 40% (within the 35–45% target band); location/physical are demoted
    so a good *building* or good *operating location* can no longer, on its own,
    manufacture an Approved verdict — that requires the financial gates too.
    ``economics`` is the financial-return sub-score.
    """
    location: float = 0.18
    economics: float = 0.40
    physical_fit: float = 0.12
    competition: float = 0.10
    risk: float = 0.12
    secondary_revenue: float = 0.08


@dataclass(frozen=True)
class ScoringThresholds:
    """
    * ``>= 75``   potential approval (gated — see UnderwritingGates)
    * ``40-74``   manual_review (real-world good deals belong here)
    * ``<  40``   rejected

    NOTE: a score >= approved_min is necessary but NOT sufficient for
    ``approved_candidate``. The deterministic hard gates in
    ``UnderwritingGates`` must also all pass and confidence must be adequate.
    """
    approved_min: int = 75
    manual_review_min: int = 40

    high_confidence_min_fields: int = 9
    low_confidence_max_fields: int = 4


@dataclass(frozen=True)
class ConfidenceCaps:
    """Caps applied to the FINAL score when input data is missing/uncertain.

    Confidence is a *ceiling*, never additive points. High-conviction approval
    is impossible without adequately evidenced economics + feasibility.
    """
    # Any critical financial field missing (price/rent, floor area) -> hard cap.
    critical_missing_max_score: int = 59
    # Several operational/location fields missing -> softer cap.
    operational_missing_max_score: int = 69
    # Minimum confidence % required to allow an APPROVED verdict.
    min_confidence_pct_for_approval: float = 60.0
    # Field-count band that counts as "several operational fields missing".
    operational_missing_field_threshold: int = 6


@dataclass(frozen=True)
class UnderwritingGates:
    """Deterministic financial gates. A deal that fails a mandatory gate cannot
    be Approved regardless of its weighted score — it is demoted to manual
    review (soft fail) or rejected (severe fail).

    Sources (see ASSUMPTIONS_SOURCES for full citations):
      * Laundromat EBITDA margin 20–35% typical; <15% weak — BusinessDojo /
        VantaInsights / The Deal Sheet, 2026.
      * Base-case payback 34–50 months (2.8–4.2y); bear >60 months (>5y) —
        BusinessDojo laundromat statistics, 2026.
      * Rent 15–25% of sales sustainable — BusinessDojo cost structure, 2026.
      * Business IRR 15–30%; commercial property yields lower, so a property-
        inclusive EBITDA yield hurdle of ~8% is conservative — derived.
    """

    # --- BUY gates -------------------------------------------------------
    buy_min_stabilised_ebitda_eur: float = 0.0          # must be positive
    buy_min_downside_ebitda_eur: float = 0.0            # downside must survive
    buy_min_ebitda_yield_on_total: float = 0.08        # 8% on total investment
    buy_review_ebitda_yield_on_total: float = 0.05     # below -> review floor
    buy_max_payback_years: float = 6.0                  # approve <= 6y
    buy_review_max_payback_years: float = 9.0           # review <= 9y, else weak
    buy_max_price_per_m2_eur: float = 6000.0           # Barcelona commercial ceiling
    buy_overpriced_requires_yield: float = 0.10        # if >ceiling need >=10% yield

    # --- RENT gates ------------------------------------------------------
    rent_max_rent_to_revenue: float = 0.25             # <=25% sustainable
    rent_hardfail_rent_to_revenue: float = 0.35        # >35% -> reject
    rent_min_stabilised_ebitda_eur: float = 0.0
    rent_min_downside_ebitda_eur: float = 0.0
    rent_min_ebitda_margin: float = 0.12               # <12% weak
    rent_max_payback_years: float = 4.0                # fit-out/equip payback
    rent_review_max_payback_years: float = 6.0

    # --- Shared ----------------------------------------------------------
    min_ebitda_margin_for_approval: float = 0.15       # 15% floor for approval


@dataclass(frozen=True)
class TransactionCosts:
    """Catalonia commercial resale acquisition costs (buy only).

    ITP (Impuesto de Transmisiones Patrimoniales) is progressive from
    27 Jun 2025 (Decret llei 5/2025). Notary/registry/legal/gestoria add
    ~1.6% combined. New-build (IVA 10% + AJD) is not modelled here; ITP resale
    is the conservative default and is override-able.
    """
    # Progressive ITP brackets: (upper_bound_eur, rate). Last bound = inf.
    itp_brackets: Tuple[Tuple[float, float], ...] = (
        (600_000.0, 0.10),
        (900_000.0, 0.11),
        (1_500_000.0, 0.12),
        (float("inf"), 0.13),
    )
    notary_pct: float = 0.004      # ~0.2–0.5% regulated
    registry_pct: float = 0.002    # ~0.1–0.25%
    legal_pct: float = 0.010       # ~1% + IVA independent lawyer
    gestoria_eur: float = 500.0    # fixed admin


@dataclass(frozen=True)
class LocationBaseline:
    population_density_per_km2: float = 14_000.0
    apartment_density_pct: float = 0.62
    median_household_income_eur: float = 32_500.0
    students_within_1km: int = 1_200
    hotels_within_500m: int = 4
    universities_within_2km: int = 0
    nearby_laundromats_within_500m: int = 3
    competitors_within_1km: int = 7
    walkability_score_0_100: int = 70
    night_safety_0_100: int = 65


@dataclass(frozen=True)
class BusinessProfile:
    """Operator-facing rules of thumb (independent of the financial model)."""

    ideal_floor_area_m2: float = 70.0
    min_viable_floor_area_m2: float = 35.0
    max_recommended_floor_area_m2: float = 80.0
    hard_max_floor_area_m2: float = 110.0
    target_total_machines: int = 10

    target_city: str = "Barcelona"
    preferred_neighbourhoods: Tuple[str, ...] = (
        "Raval",
        "Sant Antoni",
        "Poble Sec",
        "Clot",
        "Hospitalet",
        "L'Hospitalet",
    )

    target_renter_pct_min: float = 0.45
    target_small_housing_pct_min: float = 0.40
    target_population_density_min: float = 9_000.0
    target_population_density_max: float = 28_000.0
    target_income_band_eur: Tuple[float, float] = (16_000.0, 38_000.0)

    rent_capex_discount_pct: float = 0.0
    franchise_royalty_pct_of_revenue: float = 0.06
    franchise_initial_fee_eur: float = 18_000.0


# Bump this whenever scoring logic or calibration constants change. Persisted
# with every analysis so historical scores stay attributable + rescoreable.
SCORING_VERSION = "kua-laundry-3.0"

# External calibration provenance (source, date, unit, note). Kept here as the
# single documented reference — do NOT hardcode market numbers elsewhere.
ASSUMPTIONS_SOURCES: Dict[str, Dict[str, str]] = {
    "itp_catalonia_progressive": {
        "value": "10% / 11% / 12% / 13% by price bracket",
        "unit": "% of purchase price (progressive)",
        "date": "2026 (Decret llei 5/2025, in force 27 Jun 2025)",
        "source": "camiacasa.cat, barleighellis.com, casaconnecta.com (Catalonia ITP 2026)",
        "note": "Resale commercial/residential transfer tax; new-build uses IVA 10% + AJD instead.",
    },
    "transaction_costs_total": {
        "value": "11–13%",
        "unit": "% of purchase price",
        "date": "2026",
        "source": "camiacasa.cat, barleighellis.com, spainora.com",
        "note": "ITP + notary (0.2–0.5%) + registry (0.1–0.25%) + legal (~1%).",
    },
    "laundromat_ebitda_margin": {
        "value": "20–35% typical; <15% weak; 28–45% top quartile",
        "unit": "% EBITDA margin",
        "date": "2026",
        "source": "BusinessDojo, VantaInsights, The Deal Sheet; COREView (coin-op net ~8.5%)",
        "note": "Conservative approval floor set at 15%.",
    },
    "laundromat_payback": {
        "value": "34–50 months base (2.8–4.2y); bear >60 months (>5y)",
        "unit": "years",
        "date": "2026",
        "source": "BusinessDojo laundromat statistics 2026",
        "note": "Buy approval payback <=6y; rent fit-out payback <=4y.",
    },
    "laundromat_revenue_per_machine": {
        "value": "€6k–8k/machine/yr (top 10–12k); 4–6 turns/day",
        "unit": "EUR/machine/year",
        "date": "2026",
        "source": "The Deal Sheet 2026",
        "note": "Sanity bound for fleet-driven revenue model.",
    },
    "barcelona_commercial_rent": {
        "value": "Eixample avg ~20–31 €/m²/mo; prime axes 88–343",
        "unit": "EUR/m²/month",
        "date": "Jul 2026",
        "source": "idealista commercial listings (Sagrada Família 20.11, Sant Antoni 30.58)",
        "note": "Used for rent affordability sanity, not a hard gate.",
    },
    "barcelona_commercial_sale": {
        "value": "used ~4,500–6,000 €/m² (Eixample/Consell de Cent)",
        "unit": "EUR/m²",
        "date": "Jul 2026",
        "source": "El Periódico / Laborde Marcet–Grupo ST, Jul 2026",
        "note": "Price-per-m² ceiling for buy affordability set at 6,000.",
    },
}


@dataclass(frozen=True)
class LaundryAssumptions:
    machine: MachineAssumptions = field(default_factory=MachineAssumptions)
    machine_mix: MachineMix = field(default_factory=MachineMix)
    secondary_revenue: SecondaryRevenue = field(default_factory=SecondaryRevenue)
    fit_out: FitOutAssumptions = field(default_factory=FitOutAssumptions)
    opex: OpexAssumptions = field(default_factory=OpexAssumptions)
    scoring_weights: ScoringWeights = field(default_factory=ScoringWeights)
    thresholds: ScoringThresholds = field(default_factory=ScoringThresholds)
    confidence_caps: ConfidenceCaps = field(default_factory=ConfidenceCaps)
    gates: UnderwritingGates = field(default_factory=UnderwritingGates)
    transaction_costs: TransactionCosts = field(default_factory=TransactionCosts)
    location_baseline: LocationBaseline = field(default_factory=LocationBaseline)
    business_profile: BusinessProfile = field(default_factory=BusinessProfile)

    rent_capex_discount_pct: float = 0.0
    franchise_royalty_pct_of_revenue: float = 0.06
    franchise_initial_fee_eur: float = 18_000.0
    scoring_version: str = SCORING_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_DEFAULT = LaundryAssumptions()


def default_assumptions() -> LaundryAssumptions:
    return _DEFAULT


def merge_overrides(base: LaundryAssumptions, overrides: Dict[str, Any] | None) -> LaundryAssumptions:
    """Apply nested JSON overrides — unknown keys ignored for forward-compat."""
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
                    else:
                        kwargs[f.name] = type(current)(patch[f.name])
                except (TypeError, ValueError):
                    kwargs[f.name] = current
            else:
                kwargs[f.name] = current
        return type(dc)(**kwargs)

    return _merge(base, overrides)
