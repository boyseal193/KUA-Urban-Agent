"""
Tunable assumptions for the laundromat underwriting engine.

Every constant in this module can be overridden at runtime by writing a row
into the ``laundry_settings.overrides`` JSONB column (see
:mod:`app.laundry.repository`). The numbers below are the *default* book
values used by the deterministic financial model.

Sources / sanity bands (Spain / EU urban laundromat market, 2024-2026):

* Self-service laundry revenue per machine: €18 – €60 / day for a busy urban site.
* Industrial washer (10 – 22 kg) capex: €4 500 – €11 000 / unit.
* Industrial dryer (10 – 23 kg) capex: €3 200 – €7 800 / unit.
* Fit-out (electrics, plumbing, ventilation, flooring, signage): €450 – €900 / m².
* Operating margin for a well-run unmanaged location: 30 – 45 % EBITDA.
* Cashflow payback for a quality acquisition: 3 – 6 years.

Right-sizing
------------

The K.U.A. operators target *small, dense urban* laundromats: roughly
60 – 80 m² with ~10 machines and room for secondary revenue (lockers,
vending, drop-off). Larger stores are not automatically better — they
cost more to fit out and run, with diminishing returns on cycles. The
engine therefore treats 70 m² as the *ideal* footprint and penalises
both undersized (< 35 m²) and oversized (> 110 m²) candidates.

All values are conservative — designed so real-world good deals land mostly in
the *manual_review* bucket rather than auto-rejected or auto-approved.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class MachineMix:
    """
    Configurable machine layout used by the financial model.

    The engine never hard-codes a fleet — every count below is overridable
    per-deployment from ``laundry_settings.overrides.machine_mix``.

    Defaults reflect a balanced 10-machine urban unit (5 small washers,
    2 large washers, 2 stacking dryers, 1 service unit for soap / snacks).
    """

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
    """Per-machine investment + utility consumption defaults."""

    # Capex (€)
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

    # Effective installation footprint per machine (m²). A 14 kg Speed Queen
    # is ~0.6 m² physically but planners reserve ~2.5 m² each to cover front
    # clearance, drain pan, service access, and aisle re-use. Stacking dryers
    # double up the same floor tile and are therefore cheaper on m² but more
    # expensive per unit.
    washer_footprint_m2: float = 2.5
    dryer_footprint_m2: float = 2.5
    stacking_dryer_footprint_m2: float = 1.6
    aisle_seating_ratio: float = 0.45  # share of floor area kept for circulation + seating + folding

    # Cycles per day per machine (industry typical: 3-6 in steady-state).
    avg_cycles_per_washer_day: float = 4.5
    avg_cycles_per_large_washer_day: float = 3.8
    avg_cycles_per_dryer_day: float = 4.0
    avg_revenue_per_wash_cycle_eur: float = 5.50
    avg_revenue_per_large_wash_cycle_eur: float = 8.50
    avg_revenue_per_dry_cycle_eur: float = 3.50

    # Utility consumption per cycle (industry averages for 10-14kg commercial)
    water_litres_per_wash: float = 60.0
    water_litres_per_large_wash: float = 95.0
    electricity_kwh_per_wash: float = 0.75
    electricity_kwh_per_dry: float = 3.20
    gas_kwh_per_dry: float = 4.50  # assumes gas-heated dryers when available


@dataclass(frozen=True)
class SecondaryRevenue:
    """Annual gross revenue (€) the underwriter assigns to each ancillary line.

    Only ancillaries the store is *physically capable of hosting* are added —
    e.g. an Amazon locker requires street frontage, an ATM requires a power
    drop and CCTV. The scoring engine separately rewards properties that
    could realistically host the high-value lines.
    """

    amazon_locker_eur_year: float = 4_800.0
    inpost_locker_eur_year: float = 3_600.0
    detergent_vending_eur_year: float = 2_400.0
    snack_vending_eur_year: float = 2_900.0
    drink_vending_eur_year: float = 2_600.0
    atm_eur_year: float = 1_800.0
    advertising_eur_year: float = 1_500.0
    drop_off_service_eur_year: float = 9_500.0           # pickup / drop-off wash & fold
    commercial_contract_eur_year: float = 14_000.0       # hotel / hostel / Airbnb wash contracts
    dry_cleaning_partner_eur_year: float = 2_400.0       # commission from drop-off partner


@dataclass(frozen=True)
class FitOutAssumptions:
    """Conversion + first-day-on-site costs (€)."""

    fit_out_eur_per_m2: float = 650.0          # generic build-out (floor / walls / lighting)
    electrical_upgrade_eur_per_m2: float = 95.0
    plumbing_upgrade_eur_per_m2: float = 70.0
    ventilation_eur_per_m2: float = 55.0
    drainage_upgrade_eur_per_m2: float = 40.0

    # Lump-sum line items
    gas_connection_eur: float = 6_500.0
    water_supply_upgrade_eur: float = 3_200.0
    signage_branding_eur: float = 4_800.0
    legal_costs_eur: float = 3_500.0
    licensing_permits_eur: float = 2_200.0
    initial_marketing_eur: float = 3_000.0
    working_capital_months: float = 3.0        # months of opex held as runway


@dataclass(frozen=True)
class OpexAssumptions:
    """Recurring operating costs (€/year unless noted)."""

    # Per-area utilities (baseline lighting / HVAC / standby, on top of per-cycle costs)
    base_electricity_eur_per_m2_year: float = 14.0
    base_water_eur_per_m2_year: float = 4.0

    # Variable utility unit prices
    electricity_eur_per_kwh: float = 0.21
    gas_eur_per_kwh: float = 0.085
    water_eur_per_m3: float = 2.65          # m³ = 1 000 L

    # Fixed overheads
    insurance_eur_per_year: float = 1_650.0
    internet_eur_per_year: float = 480.0
    waste_eur_per_year: float = 720.0
    cleaning_eur_per_m2_year: float = 22.0
    supplies_eur_per_m2_year: float = 11.0
    maintenance_pct_of_revenue: float = 0.05

    # Staff — unmanaged stores still need a manager 8 h/week + attendant turns
    monthly_part_time_attendant_eur: float = 720.0
    monthly_remote_manager_eur: float = 280.0


@dataclass(frozen=True)
class ScoringWeights:
    """Sum of weights does not need to equal 1 — they are normalised at runtime."""

    location: float = 0.30
    economics: float = 0.28
    physical_fit: float = 0.18
    competition: float = 0.12
    risk: float = 0.08
    secondary_revenue: float = 0.04   # potential to host lockers / vending / partner deals


@dataclass(frozen=True)
class ScoringThresholds:
    """Score → lifecycle bucket.

    Tuned to the operator brief:

    * ``>= 75``   approved_candidate (EXCELLENT)
    * ``40-74``   manual_review (REAL-WORLD GOOD, NEEDS DD)
    * ``< 40``    rejected
    """

    approved_min: int = 75
    manual_review_min: int = 40

    # Confidence ramp — the more critical fields we have, the higher the confidence.
    high_confidence_min_fields: int = 9
    low_confidence_max_fields: int = 4


@dataclass(frozen=True)
class LocationBaseline:
    """Default neighbourhood inputs when geocoding / external APIs return nothing."""

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
    """Operator-facing rules of thumb that steer the underwriter.

    These do NOT change the financial model directly — they steer the
    scoring engine + the deal triage logic so the platform favours the
    kind of properties the team actually wants to buy / lease.
    """

    # Right-sizing
    ideal_floor_area_m2: float = 70.0
    min_viable_floor_area_m2: float = 35.0
    max_recommended_floor_area_m2: float = 80.0
    hard_max_floor_area_m2: float = 110.0
    target_total_machines: int = 10

    # Preferred markets (case-insensitive substring match against
    # neighbourhood + city + address). Order is significant — the first
    # match wins for reporting purposes.
    target_city: str = "Barcelona"
    preferred_neighbourhoods: Tuple[str, ...] = (
        "Raval",
        "Sant Antoni",
        "Poble Sec",
        "Clot",
        "Hospitalet",
        "L'Hospitalet",
    )

    # Demographic targeting (boosts the location sub-score when present)
    target_renter_pct_min: float = 0.45
    target_small_housing_pct_min: float = 0.40   # share of <70 m² dwellings
    target_population_density_min: float = 9_000.0
    target_population_density_max: float = 28_000.0
    target_income_band_eur: Tuple[float, float] = (16_000.0, 38_000.0)

    # Acquisition-type modifiers
    rent_capex_discount_pct: float = 0.0
    franchise_royalty_pct_of_revenue: float = 0.06
    franchise_initial_fee_eur: float = 18_000.0


@dataclass(frozen=True)
class LaundryAssumptions:
    machine: MachineAssumptions = field(default_factory=MachineAssumptions)
    machine_mix: MachineMix = field(default_factory=MachineMix)
    secondary_revenue: SecondaryRevenue = field(default_factory=SecondaryRevenue)
    fit_out: FitOutAssumptions = field(default_factory=FitOutAssumptions)
    opex: OpexAssumptions = field(default_factory=OpexAssumptions)
    scoring_weights: ScoringWeights = field(default_factory=ScoringWeights)
    thresholds: ScoringThresholds = field(default_factory=ScoringThresholds)
    location_baseline: LocationBaseline = field(default_factory=LocationBaseline)
    business_profile: BusinessProfile = field(default_factory=BusinessProfile)

    # Acquisition-type modifiers (kept at top level for back-compat with v1 overrides)
    rent_capex_discount_pct: float = 0.0
    franchise_royalty_pct_of_revenue: float = 0.06
    franchise_initial_fee_eur: float = 18_000.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_DEFAULT = LaundryAssumptions()


def default_assumptions() -> LaundryAssumptions:
    return _DEFAULT


def merge_overrides(base: LaundryAssumptions, overrides: Dict[str, Any] | None) -> LaundryAssumptions:
    """
    Return a new ``LaundryAssumptions`` with the supplied JSON overrides applied.

    ``overrides`` follows the same nested shape as ``LaundryAssumptions.to_dict()``.
    Unknown keys are silently dropped to keep API forward-compatibility.
    """
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
                    kwargs[f.name] = type(current)(patch[f.name])
                except (TypeError, ValueError):
                    kwargs[f.name] = current
            else:
                kwargs[f.name] = current
        return type(dc)(**kwargs)

    return _merge(base, overrides)
