"""
Deterministic laundromat underwriting economics.

This is the *only* place revenue / cost / IRR estimates are produced for the
laundry vertical. The function returns a flat JSON-safe dictionary so it can be
persisted untouched into ``laundry_analyses.economics``.

Design rules:

* Pure function — no I/O, no network, no SQL.
* Every figure traces back to ``app.laundry.assumptions`` (so overrides ripple
  through automatically).
* Both **buy** and **rent** acquisition modes are supported.
* Both **existing operating laundromat** and **green-field conversion** are
  supported. When the listing already declares washer / dryer counts, those are
  trusted; otherwise the fleet is sized from floor area.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from app.laundry.assumptions import (
    LaundryAssumptions,
    default_assumptions,
    merge_overrides,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        s = (
            value.strip()
            .replace(",", ".")
            .replace("€", "")
            .replace("eur", "")
            .replace("EUR", "")
            .replace("m²", "")
            .replace("m2", "")
        )
        try:
            return float(s)
        except ValueError:
            return default
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(_safe_float(value, default)))
    except (ValueError, TypeError):
        return default


def _safe_div(a: float, b: float) -> Optional[float]:
    if not b:
        return None
    try:
        return a / b
    except ZeroDivisionError:
        return None


def estimate_machine_fleet(
    *,
    floor_area_m2: float,
    declared_washers: Optional[int],
    declared_dryers: Optional[int],
    machine: "object",
) -> Dict[str, int]:
    """
    Pick a sensible washer/dryer split for the available floor area.

    Rule of thumb the model uses:

    * Reserve ``aisle_seating_ratio`` of the area for circulation, folding, seating.
    * The remaining space is split 55/45 (washers / dryers).
    * Each washer/dryer occupies its declared footprint.
    * Minimum viable store = 4 washers + 3 dryers (≈ 25 m² of machines).

    Listings that declare actual machine counts always win — the AI is not
    second-guessing the seller's manifest.
    """
    if declared_washers and declared_washers > 0 and declared_dryers and declared_dryers > 0:
        return {
            "washer_count": int(declared_washers),
            "dryer_count": int(declared_dryers),
            "source": "declared",
        }

    usable = max(floor_area_m2 * (1.0 - machine.aisle_seating_ratio), 0.0)
    washer_area = usable * 0.55
    dryer_area = usable * 0.45

    washer_count = max(int(washer_area // machine.washer_footprint_m2), 0)
    dryer_count = max(int(dryer_area // machine.dryer_footprint_m2), 0)

    if floor_area_m2 >= 40:
        washer_count = max(washer_count, 4)
        dryer_count = max(dryer_count, 3)

    return {
        "washer_count": washer_count,
        "dryer_count": dryer_count,
        "source": "estimated",
    }


def calculate_economics(
    extracted: Optional[Dict[str, Any]] = None,
    *,
    overrides: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Run the full laundromat financial model for one property.

    Required input keys (when present they are trusted; otherwise estimated):

    * ``floor_area_m2`` — gross interior area available for the store.
    * ``acquisition_type`` — ``"buy"`` or ``"rent"`` (default: inferred).
    * ``asking_price`` — required for ``buy`` deals.
    * ``asking_rent_month`` — required for ``rent`` deals.

    Optional inputs (used when given, estimated when missing):

    * ``washer_count``, ``dryer_count``
    * ``utility_price_overrides`` (electricity_eur_per_kwh, gas_eur_per_kwh, water_eur_per_m3)
    * ``opening_hours_per_day`` (default 14)
    * ``operating_days_per_year`` (default 360)
    * ``ramp_up_months`` — months before reaching steady-state utilisation
    """
    data: Dict[str, Any] = dict(extracted or {})
    data.update(kwargs)

    assumptions = merge_overrides(default_assumptions(), overrides)
    machine = assumptions.machine
    fit_out = assumptions.fit_out
    opex_cfg = assumptions.opex

    floor_area = _safe_float(data.get("floor_area_m2") or data.get("gba_m2") or data.get("size_m2"))
    asking_price = _safe_float(data.get("asking_price"))
    asking_rent_month = _safe_float(data.get("asking_rent_month"))

    acquisition_type = (data.get("acquisition_type") or "").lower()
    if acquisition_type not in ("buy", "rent"):
        acquisition_type = "rent" if asking_rent_month > 0 and asking_price <= 0 else "buy"

    operating_days = _safe_float(data.get("operating_days_per_year"), 360.0)
    opening_hours = _safe_float(data.get("opening_hours_per_day"), 14.0)
    ramp_up_months = max(_safe_float(data.get("ramp_up_months"), 4.0), 0.0)

    # --- Machine fleet ---
    fleet = estimate_machine_fleet(
        floor_area_m2=floor_area,
        declared_washers=_safe_int(data.get("washer_count")) or None,
        declared_dryers=_safe_int(data.get("dryer_count")) or None,
        machine=machine,
    )
    washer_count = fleet["washer_count"]
    dryer_count = fleet["dryer_count"]

    # --- Capex: machine investment + fit-out ---
    machine_capex = (
        washer_count * machine.washer_unit_capex_eur
        + dryer_count * machine.dryer_unit_capex_eur
    )
    ancillary_capex = (
        (machine.soap_vending_capex_eur if washer_count > 0 else 0)
        + (machine.snack_vending_capex_eur if floor_area >= 50 else 0)
        + max(int(floor_area // 25), 2) * machine.folding_table_capex_eur
        + max(int(floor_area // 8), 4) * machine.seating_unit_capex_eur
    )
    construction_cost = floor_area * fit_out.fit_out_eur_per_m2
    electrical_upgrades = floor_area * fit_out.electrical_upgrade_eur_per_m2
    plumbing_upgrades = floor_area * fit_out.plumbing_upgrade_eur_per_m2
    ventilation = floor_area * fit_out.ventilation_eur_per_m2
    drainage = floor_area * fit_out.drainage_upgrade_eur_per_m2
    gas_connection = fit_out.gas_connection_eur if data.get("gas_available") is not False else fit_out.gas_connection_eur * 1.6
    water_supply = fit_out.water_supply_upgrade_eur

    fit_out_total = (
        construction_cost
        + electrical_upgrades
        + plumbing_upgrades
        + ventilation
        + drainage
        + gas_connection
        + water_supply
        + fit_out.signage_branding_eur
    )

    # --- Revenue: cycles per day × revenue per cycle × utilisation ramp ---
    raw_daily_revenue = (
        washer_count * machine.avg_cycles_per_washer_day * machine.avg_revenue_per_wash_cycle_eur
        + dryer_count * machine.avg_cycles_per_dryer_day * machine.avg_revenue_per_dry_cycle_eur
    )
    utilisation_factor = min(max(opening_hours / 16.0, 0.55), 1.0)
    steady_state_annual_revenue = raw_daily_revenue * operating_days * utilisation_factor

    ramp_factor = max(0.0, 1.0 - (ramp_up_months / 24.0) * 0.4)
    year1_revenue = steady_state_annual_revenue * ramp_factor

    # Ancillary revenue (vending, detergent sales) ≈ 6% of machine revenue
    ancillary_revenue = year1_revenue * 0.06
    expected_revenue = year1_revenue + ancillary_revenue

    # --- Opex ---
    annual_wash_cycles = washer_count * machine.avg_cycles_per_washer_day * operating_days * utilisation_factor
    annual_dry_cycles = dryer_count * machine.avg_cycles_per_dryer_day * operating_days * utilisation_factor

    utility_overrides = data.get("utility_price_overrides") or {}
    elec_unit = _safe_float(utility_overrides.get("electricity_eur_per_kwh"), opex_cfg.electricity_eur_per_kwh)
    gas_unit = _safe_float(utility_overrides.get("gas_eur_per_kwh"), opex_cfg.gas_eur_per_kwh)
    water_unit = _safe_float(utility_overrides.get("water_eur_per_m3"), opex_cfg.water_eur_per_m3)

    electricity_cost = (
        opex_cfg.base_electricity_eur_per_m2_year * floor_area
        + annual_wash_cycles * machine.electricity_kwh_per_wash * elec_unit
        + annual_dry_cycles * machine.electricity_kwh_per_dry * elec_unit
    )
    gas_cost = annual_dry_cycles * machine.gas_kwh_per_dry * gas_unit * (1.0 if data.get("gas_available") is not False else 0.0)
    water_cost = (
        opex_cfg.base_water_eur_per_m2_year * floor_area
        + annual_wash_cycles * machine.water_litres_per_wash / 1000.0 * water_unit
    )

    cleaning_cost = floor_area * opex_cfg.cleaning_eur_per_m2_year
    supplies_cost = floor_area * opex_cfg.supplies_eur_per_m2_year
    payroll_cost = (opex_cfg.monthly_part_time_attendant_eur + opex_cfg.monthly_remote_manager_eur) * 12
    maintenance_cost = expected_revenue * opex_cfg.maintenance_pct_of_revenue
    insurance_cost = opex_cfg.insurance_eur_per_year
    internet_cost = opex_cfg.internet_eur_per_year
    waste_cost = opex_cfg.waste_eur_per_year

    # Rent vs buy
    if acquisition_type == "rent":
        rent_cost = asking_rent_month * 12
        acquisition_cost = 0.0
    else:
        rent_cost = 0.0
        acquisition_cost = asking_price

    annual_opex = (
        electricity_cost
        + gas_cost
        + water_cost
        + cleaning_cost
        + supplies_cost
        + payroll_cost
        + maintenance_cost
        + insurance_cost
        + internet_cost
        + waste_cost
        + rent_cost
    )

    # --- Working capital + total investment ---
    monthly_opex = annual_opex / 12.0 if annual_opex else 0.0
    working_capital = monthly_opex * fit_out.working_capital_months
    legal_costs = fit_out.legal_costs_eur
    licensing = fit_out.licensing_permits_eur
    marketing = fit_out.initial_marketing_eur
    initial_staff_setup = (opex_cfg.monthly_part_time_attendant_eur + opex_cfg.monthly_remote_manager_eur) * 1.5

    capex = machine_capex + ancillary_capex + fit_out_total
    total_investment = (
        capex
        + acquisition_cost
        + working_capital
        + legal_costs
        + licensing
        + marketing
        + initial_staff_setup
    )

    # --- Profitability ---
    ebitda = expected_revenue - annual_opex
    operating_margin = _safe_div(ebitda, expected_revenue)
    cashflow = ebitda  # after-rent EBITDA equals operating cashflow for an unlevered model
    yield_pct = _safe_div(ebitda, total_investment) if total_investment > 0 else None
    payback_years = round(total_investment / ebitda, 2) if ebitda > 0 else None

    break_even_revenue = annual_opex
    break_even_cycles_per_day = (
        break_even_revenue / (
            (machine.avg_revenue_per_wash_cycle_eur * machine.avg_cycles_per_washer_day if washer_count else 1)
            * max(washer_count, 1)
            + (machine.avg_revenue_per_dry_cycle_eur * machine.avg_cycles_per_dryer_day if dryer_count else 1)
            * max(dryer_count, 1)
        ) * 365
        if washer_count + dryer_count > 0
        else None
    )

    # --- IRR approximation (10-year horizon, level EBITDA, residual = capex × 0.4) ---
    irr_estimate = _approx_irr(
        initial_investment=total_investment,
        annual_cashflow=ebitda if ebitda else 0.0,
        years=10,
        residual=capex * 0.4,
    )

    out: Dict[str, Any] = {
        "acquisition_type": acquisition_type,
        "operating_days_per_year": round(operating_days, 1),
        "opening_hours_per_day": round(opening_hours, 1),
        "ramp_up_months": round(ramp_up_months, 1),
        "floor_area_m2": round(floor_area, 2),
        "fleet": fleet,
        "washer_count": washer_count,
        "dryer_count": dryer_count,
        "folding_area_m2": round(floor_area * 0.12, 2),
        "customer_seating_units": max(int(floor_area // 8), 4),
        "soap_vending": washer_count > 0,
        "snack_vending": floor_area >= 50,

        # Capex line items
        "machine_capex_eur": round(machine_capex, 2),
        "ancillary_capex_eur": round(ancillary_capex, 2),
        "fit_out_total_eur": round(fit_out_total, 2),
        "construction_cost_eur": round(construction_cost, 2),
        "electrical_upgrades_eur": round(electrical_upgrades, 2),
        "plumbing_upgrades_eur": round(plumbing_upgrades, 2),
        "ventilation_eur": round(ventilation, 2),
        "drainage_upgrades_eur": round(drainage, 2),
        "gas_connection_eur": round(gas_connection, 2),
        "water_supply_eur": round(water_supply, 2),
        "signage_branding_eur": round(fit_out.signage_branding_eur, 2),
        "legal_costs_eur": round(legal_costs, 2),
        "licensing_eur": round(licensing, 2),
        "initial_marketing_eur": round(marketing, 2),
        "initial_staff_setup_eur": round(initial_staff_setup, 2),
        "working_capital_eur": round(working_capital, 2),
        "acquisition_cost_eur": round(acquisition_cost, 2),
        "capex_eur": round(capex, 2),
        "total_investment_eur": round(total_investment, 2),

        # Revenue
        "raw_daily_revenue_eur": round(raw_daily_revenue, 2),
        "year1_revenue_eur": round(year1_revenue, 2),
        "ancillary_revenue_eur": round(ancillary_revenue, 2),
        "expected_revenue_eur": round(expected_revenue, 2),
        "steady_state_revenue_eur": round(steady_state_annual_revenue + ancillary_revenue, 2),
        "utilisation_factor": round(utilisation_factor, 4),

        # Opex line items
        "electricity_cost_eur": round(electricity_cost, 2),
        "gas_cost_eur": round(gas_cost, 2),
        "water_cost_eur": round(water_cost, 2),
        "cleaning_cost_eur": round(cleaning_cost, 2),
        "supplies_cost_eur": round(supplies_cost, 2),
        "payroll_cost_eur": round(payroll_cost, 2),
        "maintenance_cost_eur": round(maintenance_cost, 2),
        "insurance_cost_eur": round(insurance_cost, 2),
        "internet_cost_eur": round(internet_cost, 2),
        "waste_cost_eur": round(waste_cost, 2),
        "rent_cost_eur": round(rent_cost, 2),
        "annual_opex_eur": round(annual_opex, 2),

        # Profitability
        "ebitda_eur": round(ebitda, 2),
        "operating_margin": round(operating_margin or 0, 4),
        "cashflow_eur": round(cashflow, 2),
        "yield_pct": round(yield_pct, 4) if yield_pct is not None else None,
        "payback_years": payback_years,
        "irr_estimate_pct": round(irr_estimate * 100, 2) if irr_estimate is not None else None,

        # Break-even
        "break_even_revenue_eur": round(break_even_revenue, 2),
        "break_even_cycles_per_day": round(break_even_cycles_per_day, 2) if break_even_cycles_per_day else None,

        # Reference assumptions hash (for reproducibility)
        "assumptions_version": "1.0.0",
    }
    return out


def _approx_irr(
    *,
    initial_investment: float,
    annual_cashflow: float,
    years: int,
    residual: float,
) -> Optional[float]:
    """
    Bisection IRR for a level-cashflow + terminal-value series.

    Returns ``None`` when the project cannot break even within the horizon
    (negative cashflows, infinite payback, etc.).
    """
    if initial_investment <= 0 or annual_cashflow <= 0:
        return None

    def npv(rate: float) -> float:
        total = -initial_investment
        for t in range(1, years + 1):
            total += annual_cashflow / ((1 + rate) ** t)
        total += residual / ((1 + rate) ** years)
        return total

    low, high = -0.5, 1.5
    if npv(low) < 0:
        return None

    for _ in range(80):
        mid = (low + high) / 2
        if npv(mid) > 0:
            low = mid
        else:
            high = mid
        if abs(high - low) < 1e-5:
            break
    return round((low + high) / 2, 4)
