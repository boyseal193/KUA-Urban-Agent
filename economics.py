# economics.py

from dataclasses import dataclass
from typing import Dict, Any, Optional


DISTRICT_PRICING = {
    # Prime districts
    "eixample": 26,
    "gracia": 24,
    "les corts": 25,
    "sant gervasi": 27,
    "sarria": 27,

    # Strong middle districts
    "poblenou": 22,
    "sants": 21,
    "clot": 21,
    "sant marti": 21,
    "horta": 20,
    "guinardo": 20,

    # Lower pricing districts
    "trinitat vella": 17,
    "nou barris": 17,
    "besos": 16,
    "zona franca": 16,

    # Ciutat Vella special handling
    "raval": 20,
    "gotic": 21,
    "born": 22,
}

DEFAULT_STORAGE_REVENUE = 20


@dataclass
class EconomicsResult:
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


def get_storage_revenue(neighbourhood: str) -> float:
    if not neighbourhood:
        return DEFAULT_STORAGE_REVENUE

    n = neighbourhood.lower()

    for district, price in DISTRICT_PRICING.items():
        if district in n:
            return price

    return DEFAULT_STORAGE_REVENUE


def calculate_nra_efficiency(gba_m2: float) -> float:
    if gba_m2 >= 250:
        return 0.82
    elif gba_m2 >= 200:
        return 0.80
    else:
        return 0.78


def estimate_unit_count(nra_m2: float) -> int:
    avg_unit_size = 1.9
    return int(nra_m2 / avg_unit_size)


def calculate_conversion_capex(gba_m2: float) -> float:
    capex_per_m2 = 500
    return round(gba_m2 * capex_per_m2, 2)


def calculate_opex(annual_revenue: float) -> float:
    return round(annual_revenue * 0.30, 2)


def safe_divide(a: float, b: float) -> Optional[float]:
    if b == 0:
        return None
    return a / b


def calculate_economics(extracted: Dict[str, Any]) -> Dict[str, Any]:
    gba_m2 = extracted.get("gba_m2") or 0
    neighbourhood = extracted.get("neighbourhood") or ""
    asking_price = extracted.get("asking_price") or 0
    asking_rent_month = extracted.get("asking_rent_month")

    storage_revenue_per_m2_month = get_storage_revenue(neighbourhood)

    occupancy_rate = 0.90

    nra_efficiency = calculate_nra_efficiency(gba_m2)

    nra_m2 = round(gba_m2 * nra_efficiency, 2)

    estimated_units = estimate_unit_count(nra_m2)

    monthly_revenue = round(
        nra_m2
        * storage_revenue_per_m2_month
        * occupancy_rate,
        2
    )

    annual_revenue = round(monthly_revenue * 12, 2)

    annual_opex = calculate_opex(annual_revenue)

    conversion_capex = calculate_conversion_capex(gba_m2)

    if asking_rent_month:
        model_type = "lease"
        annual_rent = round(asking_rent_month * 12, 2)
        total_investment = conversion_capex
    else:
        model_type = "freehold"
        annual_rent = 0
        total_investment = asking_price + conversion_capex

    ebitda = round(
        annual_revenue
        - annual_opex
        - annual_rent,
        2
    )

    margin = round(
        safe_divide(ebitda, annual_revenue) or 0,
        4
    )

    if asking_price > 0:
        ebitda_yield = round(
            safe_divide(ebitda, asking_price),
            4
        )
    else:
        ebitda_yield = None

    if total_investment > 0:
        true_ebitda_yield = round(
            safe_divide(ebitda, total_investment),
            4
        )
    else:
        true_ebitda_yield = None

    if ebitda > 0:
        payback_years = round(
            asking_price / ebitda,
            2
        ) if asking_price > 0 else None

        true_payback_years = round(
            total_investment / ebitda,
            2
        )
    else:
        payback_years = None
        true_payback_years = None

    result = EconomicsResult(
        model_type=model_type,
        storage_revenue_per_m2_month=storage_revenue_per_m2_month,
        occupancy_rate=occupancy_rate,
        nra_efficiency=nra_efficiency,
        nra_m2=nra_m2,
        estimated_units=estimated_units,
        monthly_revenue=monthly_revenue,
        annual_revenue=annual_revenue,
        annual_rent=annual_rent,
        annual_opex=annual_opex,
        ebitda=ebitda,
        margin=margin,
        asking_price=asking_price,
        conversion_capex=conversion_capex,
        total_investment=total_investment,
        ebitda_yield=ebitda_yield,
        true_ebitda_yield=true_ebitda_yield,
        payback_years=payback_years,
        true_payback_years=true_payback_years,
    )

    return result.__dict__