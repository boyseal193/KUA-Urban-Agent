# economics.py — SELF-STORAGE deterministic financial model (v3)
#
# Independent of the laundromat model. Pure-Python, no I/O. Produces a flat
# JSON-safe dict. Backward-compatible: every legacy key the exports / memo /
# frontend read is still present; new underwriting fields are added alongside.

from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from storage_assumptions import (
    StorageAssumptions,
    default_assumptions,
    merge_overrides,
    get_storage_revenue,
)

# Legacy public constants (kept so any importer keeps working).
DISTRICT_PRICING = dict(default_assumptions().district_revenue.table)
DEFAULT_STORAGE_REVENUE = default_assumptions().district_revenue.default_eur_per_m2_month


@dataclass
class EconomicsResult:  # retained for backward-compat imports (unused internally)
    model_type: str
    storage_revenue_per_m2_month: float
    occupancy_rate: float
    nra_efficiency: float
    nra_m2: float
    estimated_units: int
    monthly_revenue: float
    annual_revenue: float
    annual_rent: float
    annual_opex: float
    ebitda: float
    margin: float
    asking_price: float
    conversion_capex: float
    total_investment: float
    ebitda_yield: Optional[float]
    true_ebitda_yield: Optional[float]
    payback_years: Optional[float]
    true_payback_years: Optional[float]


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = (
            value.strip().lower()
            .replace("€", "").replace("eur", "")
            .replace("m²", "").replace("m2", "").replace(",", ".")
        )
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def safe_divide(a: float, b: float) -> Optional[float]:
    if not b:
        return None
    return a / b


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------
def calculate_nra_efficiency(gba_m2: float, op=None) -> float:
    op = op or default_assumptions().operating
    if gba_m2 >= op.nra_eff_large_min_gba:
        return op.nra_eff_large
    if gba_m2 >= op.nra_eff_mid_min_gba:
        return op.nra_eff_mid
    return op.nra_eff_small


def estimate_unit_count(nra_m2: float, op=None) -> int:
    op = op or default_assumptions().operating
    if nra_m2 <= 0 or op.avg_unit_size_m2 <= 0:
        return 0
    return int(nra_m2 / op.avg_unit_size_m2)


def calculate_conversion_capex(gba_m2: float, cx=None) -> float:
    """Itemised fit-out capex (partitions/doors, fire, access/CCTV, etc.)."""
    cx = cx or default_assumptions().capex
    if gba_m2 <= 0:
        return 0.0
    per_m2 = (
        cx.partitions_doors_eur_per_m2
        + cx.lighting_ventilation_eur_per_m2
        + cx.fire_compliance_eur_per_m2
        + cx.access_control_cctv_eur_per_m2
        + cx.flooring_finishes_eur_per_m2
    )
    subtotal = gba_m2 * per_m2 + cx.reception_signage_eur + cx.professional_fees_eur + cx.permits_licence_eur
    return round(subtotal * (1.0 + cx.contingency_pct), 2)


def _capex_breakdown(gba_m2: float, cx) -> Dict[str, float]:
    if gba_m2 <= 0:
        return {}
    base = {
        "partitions_doors_eur": round(gba_m2 * cx.partitions_doors_eur_per_m2, 2),
        "lighting_ventilation_eur": round(gba_m2 * cx.lighting_ventilation_eur_per_m2, 2),
        "fire_compliance_eur": round(gba_m2 * cx.fire_compliance_eur_per_m2, 2),
        "access_control_cctv_eur": round(gba_m2 * cx.access_control_cctv_eur_per_m2, 2),
        "flooring_finishes_eur": round(gba_m2 * cx.flooring_finishes_eur_per_m2, 2),
        "reception_signage_eur": round(cx.reception_signage_eur, 2),
        "professional_fees_eur": round(cx.professional_fees_eur, 2),
        "permits_licence_eur": round(cx.permits_licence_eur, 2),
    }
    base["contingency_eur"] = round(sum(base.values()) * cx.contingency_pct, 2)
    return base


def _acquisition_transaction_costs(price: float, tx) -> Dict[str, float]:
    if price <= 0:
        return {"itp_eur": 0.0, "notary_eur": 0.0, "registry_eur": 0.0,
                "legal_eur": 0.0, "gestoria_eur": 0.0, "total_eur": 0.0, "effective_pct": 0.0}
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
    total = itp + notary + registry + legal + tx.gestoria_eur
    return {
        "itp_eur": round(itp, 2), "notary_eur": round(notary, 2),
        "registry_eur": round(registry, 2), "legal_eur": round(legal, 2),
        "gestoria_eur": round(tx.gestoria_eur, 2), "total_eur": round(total, 2),
        "effective_pct": round(total / price, 4),
    }


def _opex_for(revenue: float, nra_m2: float, purchase_price: float, is_buy: bool, op) -> float:
    fixed = nra_m2 * op.opex_fixed_eur_per_nra_m2_year
    variable = revenue * op.opex_variable_pct_of_revenue
    property_tax = purchase_price * op.property_tax_pct_of_price if is_buy else 0.0
    return fixed + variable + property_tax


def _case(*, occupancy: float, nra_m2: float, rev_per_m2_month: float,
          annual_rent: float, purchase_price: float, is_buy: bool, op) -> Dict[str, float]:
    annual_revenue = nra_m2 * rev_per_m2_month * 12.0 * occupancy
    opex = _opex_for(annual_revenue, nra_m2, purchase_price, is_buy, op)
    ebitda = annual_revenue - opex - annual_rent
    return {
        "occupancy": round(occupancy, 4),
        "annual_revenue_eur": round(annual_revenue, 2),
        "annual_opex_eur": round(opex, 2),
        "ebitda_eur": round(ebitda, 2),
    }


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
def calculate_economics(
    extracted: Optional[Dict[str, Any]] = None,
    *,
    gba_m2: Optional[float] = None,
    neighbourhood: Optional[str] = None,
    asking_price: Optional[float] = None,
    asking_rent_month: Optional[float] = None,
    rent_per_m2: Optional[float] = None,
    price_per_m2_nra: Optional[float] = None,
    nra_efficiency: Optional[float] = None,
    overrides: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Self-storage economics. Supports dict-style and legacy keyword-style calls."""
    data: Dict[str, Any] = dict(extracted or {})
    for k, v in (
        ("gba_m2", gba_m2), ("neighbourhood", neighbourhood), ("asking_price", asking_price),
        ("asking_rent_month", asking_rent_month), ("rent_per_m2", rent_per_m2),
        ("price_per_m2_nra", price_per_m2_nra), ("nra_efficiency", nra_efficiency),
    ):
        if v is not None:
            data[k] = v

    assumptions: StorageAssumptions = merge_overrides(default_assumptions(), overrides)
    op = assumptions.operating
    cx = assumptions.capex
    tx = assumptions.transaction_costs

    gba = _safe_float(data.get("gba_m2"), 0.0)
    district = str(data.get("neighbourhood") or data.get("district") or "")
    purchase_price = _safe_float(data.get("asking_price"), 0.0)
    monthly_rent = _safe_float(data.get("asking_rent_month"), 0.0)

    rev_per_m2_month = _safe_float(data.get("price_per_m2_nra"), get_storage_revenue(district, assumptions))

    efficiency = _safe_float(data.get("nra_efficiency"), 0.0)
    if efficiency <= 0:
        efficiency = calculate_nra_efficiency(gba, op)

    nra_m2 = round(gba * efficiency, 2)
    estimated_units = estimate_unit_count(nra_m2, op)

    is_buy = monthly_rent <= 0
    model_type = "freehold" if is_buy else "lease"
    annual_rent = 0.0 if is_buy else round(monthly_rent * 12.0, 2)

    stabilised_occ = op.stabilised_occupancy
    occupancy_rate = stabilised_occ  # headline occupancy (backward-compat key)

    # Cases: stabilised (base), year-1, downside, severe downside.
    stab = _case(occupancy=stabilised_occ, nra_m2=nra_m2, rev_per_m2_month=rev_per_m2_month,
                 annual_rent=annual_rent, purchase_price=purchase_price, is_buy=is_buy, op=op)
    year1 = _case(occupancy=op.year1_occupancy, nra_m2=nra_m2, rev_per_m2_month=rev_per_m2_month,
                  annual_rent=annual_rent, purchase_price=purchase_price, is_buy=is_buy, op=op)
    downside = _case(occupancy=op.downside_occupancy, nra_m2=nra_m2, rev_per_m2_month=rev_per_m2_month,
                     annual_rent=annual_rent, purchase_price=purchase_price, is_buy=is_buy, op=op)
    severe = _case(occupancy=op.severe_downside_occupancy, nra_m2=nra_m2, rev_per_m2_month=rev_per_m2_month,
                   annual_rent=annual_rent, purchase_price=purchase_price, is_buy=is_buy, op=op)

    annual_revenue = stab["annual_revenue_eur"]
    monthly_revenue = round(annual_revenue / 12.0, 2)
    annual_opex = stab["annual_opex_eur"]
    ebitda = stab["ebitda_eur"]
    margin = round(safe_divide(ebitda, annual_revenue) or 0.0, 4)

    # Capex + transaction costs + working capital -> total investment.
    conversion_capex = calculate_conversion_capex(gba, cx)
    capex_breakdown = _capex_breakdown(gba, cx)
    transaction_costs = _acquisition_transaction_costs(purchase_price, tx) if is_buy else {"total_eur": 0.0, "effective_pct": 0.0}
    acquisition_transaction_cost = float(transaction_costs.get("total_eur") or 0.0)
    working_capital = round(max(annual_opex + annual_rent, 0.0) / 12.0 * cx.working_capital_months, 2)

    if is_buy:
        total_investment = round(purchase_price + acquisition_transaction_cost + conversion_capex + working_capital, 2)
    else:
        total_investment = round(conversion_capex + working_capital, 2)

    ebitda_yield = round(safe_divide(ebitda, purchase_price) or 0.0, 4) if purchase_price > 0 else None
    true_ebitda_yield = round(safe_divide(ebitda, total_investment) or 0.0, 4) if total_investment > 0 else None
    downside_yield = round(safe_divide(downside["ebitda_eur"], total_investment) or 0.0, 4) if total_investment > 0 else None

    if ebitda > 0:
        payback_years = round(purchase_price / ebitda, 2) if purchase_price > 0 else None
        true_payback_years = round(total_investment / ebitda, 2)
    else:
        payback_years = None
        true_payback_years = None

    price_per_m2 = round(safe_divide(purchase_price, gba) or 0.0, 2) if (is_buy and gba > 0) else None
    return_on_cost = true_ebitda_yield
    rent_to_revenue = round(safe_divide(annual_rent, annual_revenue) or 0.0, 4) if (not is_buy and annual_revenue > 0) else None
    bad_debt_eur = round(annual_revenue * op.bad_debt_pct_of_revenue, 2)

    sensitivity = {"scenarios": [
        {"label": "base", **{k: stab[k] for k in ("occupancy", "annual_revenue_eur", "annual_opex_eur", "ebitda_eur")}},
        {"label": "year1", **{k: year1[k] for k in ("occupancy", "annual_revenue_eur", "annual_opex_eur", "ebitda_eur")}},
        {"label": "downside", **{k: downside[k] for k in ("occupancy", "annual_revenue_eur", "annual_opex_eur", "ebitda_eur")}},
        {"label": "severe_downside", **{k: severe[k] for k in ("occupancy", "annual_revenue_eur", "annual_opex_eur", "ebitda_eur")}},
    ]}

    return {
        # --- legacy keys (unchanged names) -------------------------------
        "model_type": model_type,
        "storage_revenue_per_m2_month": rev_per_m2_month,
        "occupancy_rate": occupancy_rate,
        "nra_efficiency": efficiency,
        "nra_m2": nra_m2,
        "estimated_units": estimated_units,
        "monthly_revenue": monthly_revenue,
        "annual_revenue": annual_revenue,
        "annual_rent": annual_rent,
        "annual_opex": annual_opex,
        "ebitda": ebitda,
        "margin": margin,
        "asking_price": purchase_price,
        "conversion_capex": conversion_capex,
        "total_investment": total_investment,
        "ebitda_yield": ebitda_yield,
        "true_ebitda_yield": true_ebitda_yield,
        "payback_years": payback_years,
        "true_payback_years": true_payback_years,
        # --- new underwriting fields -------------------------------------
        "acquisition_type": "buy" if is_buy else "rent",
        "gba_m2": round(gba, 2),
        "price_per_m2_eur": price_per_m2,
        "return_on_cost_pct": return_on_cost,
        "downside_ebitda_eur": downside["ebitda_eur"],
        "severe_downside_ebitda_eur": severe["ebitda_eur"],
        "downside_yield_pct": downside_yield,
        "year1_ebitda_eur": year1["ebitda_eur"],
        "year1_occupancy": op.year1_occupancy,
        "stabilised_occupancy": stabilised_occ,
        "rent_to_revenue_pct": rent_to_revenue,
        "annual_rent_eur": annual_rent,
        "monthly_rent_eur": monthly_rent,
        "bad_debt_eur": bad_debt_eur,
        "capex_breakdown": capex_breakdown,
        "acquisition_transaction_costs": transaction_costs,
        "acquisition_transaction_cost_eur": round(acquisition_transaction_cost, 2),
        "working_capital_eur": working_capital,
        "sensitivity": sensitivity,
        "assumptions_version": "3.0.0",
        "scoring_version": assumptions.scoring_version,
    }
