"""
Deterministic laundromat financial model.

Pure-Python: no I/O, no network, no SQL. The output is a flat JSON-safe
dict that can be persisted as-is into ``laundry_analyses.economics``.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from laundry.assumptions import LaundryAssumptions, default_assumptions, merge_overrides
from laundry.normalization import ground_floor_value


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------
def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
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


def _acquisition_transaction_costs(price: float, tx) -> Dict[str, float]:
    """Catalonia commercial resale transaction costs (progressive ITP + fees).

    See ``laundry.assumptions.TransactionCosts`` / ASSUMPTIONS_SOURCES.
    Returns a breakdown plus the total; all zero when ``price`` <= 0.
    """
    if price <= 0:
        return {"itp_eur": 0.0, "notary_eur": 0.0, "registry_eur": 0.0,
                "legal_eur": 0.0, "gestoria_eur": 0.0, "total_eur": 0.0,
                "effective_pct": 0.0}
    itp = 0.0
    lower = 0.0
    for upper, rate in tx.itp_brackets:
        if price <= lower:
            break
        taxable = min(price, upper) - lower
        if taxable > 0:
            itp += taxable * rate
        lower = upper
    notary = price * tx.notary_pct
    registry = price * tx.registry_pct
    legal = price * tx.legal_pct
    gestoria = tx.gestoria_eur
    total = itp + notary + registry + legal + gestoria
    return {
        "itp_eur": round(itp, 2),
        "notary_eur": round(notary, 2),
        "registry_eur": round(registry, 2),
        "legal_eur": round(legal, 2),
        "gestoria_eur": round(gestoria, 2),
        "total_eur": round(total, 2),
        "effective_pct": round(total / price, 4),
    }


# ---------------------------------------------------------------------------
# Fleet sizing
# ---------------------------------------------------------------------------
def estimate_machine_fleet(
    *,
    floor_area_m2: float,
    declared_washers: Optional[int],
    declared_dryers: Optional[int],
    machine,
    machine_mix=None,
    target_total_machines: Optional[int] = None,
) -> Dict[str, int]:
    if declared_washers and declared_washers > 0 and declared_dryers and declared_dryers > 0:
        return {
            "washer_count": int(declared_washers),
            "dryer_count": int(declared_dryers),
            "large_washer_count": 0,
            "stacking_dryer_count": int(declared_dryers),
            "source": "declared",
        }

    usable = max(floor_area_m2 * (1.0 - machine.aisle_seating_ratio), 0.0)
    area_washer_cap = int((usable * 0.55) // machine.washer_footprint_m2)
    area_dryer_cap = int((usable * 0.45) // machine.dryer_footprint_m2)

    if machine_mix is not None:
        target_w = max(int(machine_mix.target_washers), 0)
        target_d = max(int(machine_mix.target_dryers), 0)
        target_lg_w = max(int(machine_mix.target_large_washers), 0)
        target_stack_d = max(int(machine_mix.target_stacking_dryers), 0)
    else:
        target_w, target_d = 7, 3
        target_lg_w, target_stack_d = 2, 2

    target_total = int(target_total_machines or (target_w + target_d) or 10)

    requested_total = max(target_w + target_d, 1)
    feasible_total = min(requested_total, area_washer_cap + area_dryer_cap, target_total)
    if feasible_total <= 0 and floor_area_m2 >= 30:
        feasible_total = min(area_washer_cap + area_dryer_cap, 6)
    if feasible_total <= 0:
        return {
            "washer_count": 0,
            "dryer_count": 0,
            "large_washer_count": 0,
            "stacking_dryer_count": 0,
            "source": "no_fit",
        }

    scale = feasible_total / requested_total
    washer_count = max(
        int(round(target_w * scale)),
        min(area_washer_cap, 4) if floor_area_m2 >= 35 else 0,
    )
    dryer_count = max(feasible_total - washer_count, 0)
    if dryer_count > area_dryer_cap:
        dryer_count = area_dryer_cap
        washer_count = min(area_washer_cap, feasible_total - dryer_count)

    large_washer_count = min(washer_count, max(int(round(target_lg_w * scale)), 0))
    stacking_dryer_count = min(dryer_count, max(int(round(target_stack_d * scale)), 0))

    return {
        "washer_count": washer_count,
        "dryer_count": dryer_count,
        "large_washer_count": large_washer_count,
        "stacking_dryer_count": stacking_dryer_count,
        "source": "estimated",
    }


# ---------------------------------------------------------------------------
# Secondary revenue
# ---------------------------------------------------------------------------
def estimate_secondary_revenue(
    *,
    extracted: Dict[str, Any],
    floor_area_m2: float,
    location: Dict[str, Any],
    secondary_cfg,
) -> Dict[str, Any]:
    items: Dict[str, float] = {}
    potential: List[str] = []

    has_frontage = ground_floor_value(extracted) is not False and bool(
        extracted.get("street_visibility_0_100") or location.get("street_visibility_0_100", 65)
    )
    has_loading = bool(extracted.get("loading_access"))
    has_room_for_locker = floor_area_m2 >= 35 and has_frontage
    has_room_for_vending = floor_area_m2 >= 30
    hotels = int(location.get("hotels_within_500m") or 0)
    universities = int(location.get("universities_within_2km") or 0)
    students = int(location.get("students_within_1km") or 0)
    corner = bool(extracted.get("corner_unit"))

    if has_room_for_locker:
        items["amazon_locker_eur_year"] = secondary_cfg.amazon_locker_eur_year
        items["inpost_locker_eur_year"] = secondary_cfg.inpost_locker_eur_year * 0.65
    else:
        potential.append("parcel_lockers_need_frontage")

    if has_room_for_vending:
        items["detergent_vending_eur_year"] = secondary_cfg.detergent_vending_eur_year
        items["snack_vending_eur_year"] = secondary_cfg.snack_vending_eur_year
        if floor_area_m2 >= 55:
            items["drink_vending_eur_year"] = secondary_cfg.drink_vending_eur_year
    else:
        potential.append("vending_needs_min_30m2")

    if has_frontage and corner:
        items["atm_eur_year"] = secondary_cfg.atm_eur_year
    elif has_frontage:
        potential.append("atm_optional_if_secure_alcove")

    if has_frontage:
        items["advertising_eur_year"] = secondary_cfg.advertising_eur_year

    drop_off_multiplier = 0.0
    if hotels >= 3:
        drop_off_multiplier += 0.6
    if students >= 800:
        drop_off_multiplier += 0.4
    if universities >= 1:
        drop_off_multiplier += 0.2
    if has_loading:
        drop_off_multiplier += 0.2
    drop_off_multiplier = min(drop_off_multiplier, 1.2)

    if drop_off_multiplier > 0:
        items["drop_off_service_eur_year"] = (
            secondary_cfg.drop_off_service_eur_year * drop_off_multiplier
        )
    else:
        potential.append("drop_off_needs_tourist_or_student_demand")

    if hotels >= 4 or universities >= 1:
        items["commercial_contract_eur_year"] = secondary_cfg.commercial_contract_eur_year * (
            0.6 + min(hotels, 8) * 0.05
        )
    else:
        potential.append("commercial_contracts_need_hotel_or_uni_demand")

    if hotels >= 1 or students >= 600:
        items["dry_cleaning_partner_eur_year"] = secondary_cfg.dry_cleaning_partner_eur_year

    total = sum(items.values())
    return {
        "items_eur_year": {k: round(v, 2) for k, v in items.items()},
        "total_eur_year": round(total, 2),
        "potential_opportunities": potential,
    }


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
def calculate_economics(
    extracted: Optional[Dict[str, Any]] = None,
    *,
    overrides: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(extracted or {})
    data.update(kwargs)

    assumptions = merge_overrides(default_assumptions(), overrides)
    machine = assumptions.machine
    machine_mix = assumptions.machine_mix
    secondary_cfg = assumptions.secondary_revenue
    fit_out = assumptions.fit_out
    opex_cfg = assumptions.opex
    biz = assumptions.business_profile

    floor_area = _safe_float(data.get("floor_area_m2") or data.get("gba_m2") or data.get("size_m2"))
    asking_price = _safe_float(data.get("asking_price"))
    asking_rent_month = _safe_float(data.get("asking_rent_month"))

    acquisition_type = (data.get("acquisition_type") or "").lower()
    if acquisition_type not in ("buy", "rent"):
        acquisition_type = "rent" if asking_rent_month > 0 and asking_price <= 0 else "buy"

    operating_days = _safe_float(data.get("operating_days_per_year"), 360.0)
    opening_hours = _safe_float(data.get("opening_hours_per_day"), 14.0)
    ramp_up_months = max(_safe_float(data.get("ramp_up_months"), 4.0), 0.0)

    fleet = estimate_machine_fleet(
        floor_area_m2=floor_area,
        declared_washers=_safe_int(data.get("washer_count")) or None,
        declared_dryers=_safe_int(data.get("dryer_count")) or None,
        machine=machine,
        machine_mix=machine_mix,
        target_total_machines=biz.target_total_machines,
    )
    washer_count = fleet["washer_count"]
    dryer_count = fleet["dryer_count"]
    large_washer_count = fleet.get("large_washer_count", 0)
    standard_washer_count = max(washer_count - large_washer_count, 0)
    stacking_dryer_count = fleet.get("stacking_dryer_count", 0)
    standard_dryer_count = max(dryer_count - stacking_dryer_count, 0)

    machine_capex = (
        standard_washer_count * machine.washer_unit_capex_eur
        + large_washer_count * machine.large_washer_unit_capex_eur
        + standard_dryer_count * machine.dryer_unit_capex_eur
        + stacking_dryer_count * machine.stacking_dryer_unit_capex_eur
    )
    ancillary_capex = (
        machine_mix.detergent_vending * machine.soap_vending_capex_eur
        + machine_mix.snack_vending * machine.snack_vending_capex_eur
        + machine_mix.drink_vending * machine.drink_vending_capex_eur
        + machine_mix.payment_kiosks * machine.payment_kiosk_capex_eur
        + max(machine_mix.folding_stations, int(floor_area // 25)) * machine.folding_table_capex_eur
        + max(machine_mix.seating_units, int(floor_area // 8)) * machine.seating_unit_capex_eur
    )
    construction_cost = floor_area * fit_out.fit_out_eur_per_m2
    electrical_upgrades = floor_area * fit_out.electrical_upgrade_eur_per_m2
    plumbing_upgrades = floor_area * fit_out.plumbing_upgrade_eur_per_m2
    ventilation = floor_area * fit_out.ventilation_eur_per_m2
    drainage = floor_area * fit_out.drainage_upgrade_eur_per_m2
    gas_connection = (
        fit_out.gas_connection_eur if data.get("gas_available") is not False else fit_out.gas_connection_eur * 1.6
    )
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

    raw_daily_revenue = (
        standard_washer_count * machine.avg_cycles_per_washer_day * machine.avg_revenue_per_wash_cycle_eur
        + large_washer_count * machine.avg_cycles_per_large_washer_day * machine.avg_revenue_per_large_wash_cycle_eur
        + dryer_count * machine.avg_cycles_per_dryer_day * machine.avg_revenue_per_dry_cycle_eur
    )
    utilisation_factor = min(max(opening_hours / 16.0, 0.55), 1.0)
    steady_state_annual_revenue = raw_daily_revenue * operating_days * utilisation_factor

    ramp_factor = max(0.0, 1.0 - (ramp_up_months / 24.0) * 0.4)
    year1_revenue = steady_state_annual_revenue * ramp_factor

    in_store_ancillary_revenue = year1_revenue * 0.05

    secondary = estimate_secondary_revenue(
        extracted=data,
        floor_area_m2=floor_area,
        location=data.get("_location") or {},
        secondary_cfg=secondary_cfg,
    )
    secondary_revenue = secondary["total_eur_year"] * ramp_factor
    expected_revenue = year1_revenue + in_store_ancillary_revenue + secondary_revenue

    annual_wash_cycles = (
        standard_washer_count * machine.avg_cycles_per_washer_day * operating_days * utilisation_factor
        + large_washer_count * machine.avg_cycles_per_large_washer_day * operating_days * utilisation_factor
    )
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
    gas_cost = annual_dry_cycles * machine.gas_kwh_per_dry * gas_unit * (
        1.0 if data.get("gas_available") is not False else 0.0
    )
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

    if acquisition_type == "rent":
        rent_cost = asking_rent_month * 12
        acquisition_cost = 0.0
        transaction_costs = {"total_eur": 0.0, "effective_pct": 0.0}
    else:
        rent_cost = 0.0
        acquisition_cost = asking_price
        transaction_costs = _acquisition_transaction_costs(
            asking_price, assumptions.transaction_costs
        )

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

    monthly_opex = annual_opex / 12.0 if annual_opex else 0.0
    working_capital = monthly_opex * fit_out.working_capital_months
    legal_costs = fit_out.legal_costs_eur
    licensing = fit_out.licensing_permits_eur
    marketing = fit_out.initial_marketing_eur
    initial_staff_setup = (opex_cfg.monthly_part_time_attendant_eur + opex_cfg.monthly_remote_manager_eur) * 1.5

    acquisition_transaction_cost = float(transaction_costs.get("total_eur") or 0.0)
    capex = machine_capex + ancillary_capex + fit_out_total
    total_investment = (
        capex
        + acquisition_cost
        + acquisition_transaction_cost
        + working_capital
        + legal_costs
        + licensing
        + marketing
        + initial_staff_setup
    )

    ebitda = expected_revenue - annual_opex
    operating_margin = _safe_div(ebitda, expected_revenue)
    cashflow = ebitda
    yield_pct = _safe_div(ebitda, total_investment) if total_investment > 0 else None
    payback_years = round(total_investment / ebitda, 2) if ebitda > 0 else None

    # --- Underwriting-grade financial metrics (v3) -----------------------
    price_per_m2 = _safe_div(asking_price, floor_area) if acquisition_type == "buy" else None
    rent_per_m2_month = _safe_div(asking_rent_month, floor_area) if acquisition_type == "rent" else None
    ebitda_yield_on_total = yield_pct
    ebitda_yield_on_price = (
        _safe_div(ebitda, acquisition_cost) if acquisition_type == "buy" and acquisition_cost > 0 else None
    )
    rent_to_revenue = (
        _safe_div(rent_cost, expected_revenue) if acquisition_type == "rent" and expected_revenue > 0 else None
    )

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

    irr_estimate = _approx_irr(
        initial_investment=total_investment,
        annual_cashflow=ebitda if ebitda else 0.0,
        years=10,
        residual=capex * 0.4,
    )

    sensitivity = _sensitivity(
        baseline_revenue=expected_revenue,
        baseline_opex=annual_opex,
        baseline_capex_total=total_investment,
    )
    _downside = next(
        (s for s in sensitivity.get("scenarios", []) if s.get("label") == "downside"),
        None,
    )
    downside_ebitda = float(_downside.get("ebitda_eur")) if _downside else None
    downside_yield = (
        _safe_div(downside_ebitda, total_investment)
        if downside_ebitda is not None and total_investment > 0
        else None
    )

    right_size_flag = _right_size_status(floor_area, biz)

    return {
        "acquisition_type": acquisition_type,
        "operating_days_per_year": round(operating_days, 1),
        "opening_hours_per_day": round(opening_hours, 1),
        "ramp_up_months": round(ramp_up_months, 1),
        "floor_area_m2": round(floor_area, 2),
        "right_size_status": right_size_flag,
        "fleet": fleet,
        "washer_count": washer_count,
        "standard_washer_count": standard_washer_count,
        "large_washer_count": large_washer_count,
        "dryer_count": dryer_count,
        "standard_dryer_count": standard_dryer_count,
        "stacking_dryer_count": stacking_dryer_count,
        "total_machines": washer_count + dryer_count,
        "folding_area_m2": round(floor_area * 0.12, 2),
        "folding_stations": machine_mix.folding_stations,
        "customer_seating_units": max(machine_mix.seating_units, int(floor_area // 8)),
        "detergent_vending_units": machine_mix.detergent_vending,
        "snack_vending_units": machine_mix.snack_vending,
        "drink_vending_units": machine_mix.drink_vending,
        "payment_kiosks": machine_mix.payment_kiosks,
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
        "acquisition_transaction_costs": transaction_costs,
        "acquisition_transaction_cost_eur": round(acquisition_transaction_cost, 2),
        "capex_eur": round(capex, 2),
        "total_investment_eur": round(total_investment, 2),
        "raw_daily_revenue_eur": round(raw_daily_revenue, 2),
        "year1_revenue_eur": round(year1_revenue, 2),
        "in_store_ancillary_revenue_eur": round(in_store_ancillary_revenue, 2),
        "secondary_revenue_eur": round(secondary_revenue, 2),
        "secondary_revenue_breakdown": secondary["items_eur_year"],
        "secondary_revenue_potential": secondary["potential_opportunities"],
        "ancillary_revenue_eur": round(in_store_ancillary_revenue + secondary_revenue, 2),
        "expected_revenue_eur": round(expected_revenue, 2),
        "steady_state_revenue_eur": round(
            steady_state_annual_revenue + in_store_ancillary_revenue + secondary["total_eur_year"], 2
        ),
        "utilisation_factor": round(utilisation_factor, 4),
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
        "ebitda_eur": round(ebitda, 2),
        "operating_margin": round(operating_margin or 0, 4),
        "cashflow_eur": round(cashflow, 2),
        "yield_pct": round(yield_pct, 4) if yield_pct is not None else None,
        "ebitda_yield_on_total_pct": round(ebitda_yield_on_total, 4) if ebitda_yield_on_total is not None else None,
        "ebitda_yield_on_price_pct": round(ebitda_yield_on_price, 4) if ebitda_yield_on_price is not None else None,
        "downside_ebitda_eur": round(downside_ebitda, 2) if downside_ebitda is not None else None,
        "downside_yield_pct": round(downside_yield, 4) if downside_yield is not None else None,
        "price_per_m2_eur": round(price_per_m2, 2) if price_per_m2 is not None else None,
        "rent_per_m2_month_eur": round(rent_per_m2_month, 2) if rent_per_m2_month is not None else None,
        "rent_to_revenue_pct": round(rent_to_revenue, 4) if rent_to_revenue is not None else None,
        "payback_years": payback_years,
        "irr_estimate_pct": round(irr_estimate * 100, 2) if irr_estimate is not None else None,
        "break_even_revenue_eur": round(break_even_revenue, 2),
        "break_even_cycles_per_day": round(break_even_cycles_per_day, 2) if break_even_cycles_per_day else None,
        "sensitivity": sensitivity,
        "assumptions_version": "3.0.0",
    }


def _approx_irr(*, initial_investment, annual_cashflow, years, residual):
    if initial_investment <= 0 or annual_cashflow <= 0:
        return None

    def npv(rate):
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


def _sensitivity(*, baseline_revenue, baseline_opex, baseline_capex_total):
    scenarios = []
    for rev_shock, opex_shock, label in (
        (-0.20, +0.15, "downside"),
        (+0.00, +0.00, "base"),
        (+0.20, -0.10, "upside"),
    ):
        rev = baseline_revenue * (1 + rev_shock)
        opex = baseline_opex * (1 + opex_shock)
        ebitda = rev - opex
        payback = (baseline_capex_total / ebitda) if ebitda > 0 else None
        scenarios.append(
            {
                "label": label,
                "revenue_eur": round(rev, 2),
                "opex_eur": round(opex, 2),
                "ebitda_eur": round(ebitda, 2),
                "payback_years": round(payback, 2) if payback else None,
            }
        )
    return {"scenarios": scenarios}


def _right_size_status(floor_area: float, biz) -> str:
    if floor_area <= 0:
        return "unknown"
    if floor_area < biz.min_viable_floor_area_m2:
        return "undersized"
    if floor_area <= biz.max_recommended_floor_area_m2:
        return "ideal"
    if floor_area <= biz.hard_max_floor_area_m2:
        return "oversized_acceptable"
    return "oversized"
