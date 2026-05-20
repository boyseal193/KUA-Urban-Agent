# economics.py

from dataclasses import dataclass
from typing import Dict, Any, Optional


DISTRICT_PRICING = {
    "eixample": 26,
    "gracia": 24,
    "les corts": 25,
    "sant gervasi": 27,
    "sarria": 27,
    "poblenou": 22,
    "sants": 21,
    "clot": 21,
    "sant marti": 21,
    "horta": 20,
    "guinardo": 20,
    "trinitat vella": 17,
    "nou barris": 17,
    "besos": 16,
    "zona franca": 16,
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        cleaned = (
            value.strip()
            .lower()
            .replace("€", "")
            .replace("eur", "")
            .replace("m²", "")
            .replace("m2", "")
            .replace(",", ".")
        )

        try:
            return float(cleaned)
        except ValueError:
            return default

    return default


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
    if gba_m2 >= 200:
        return 0.80
    return 0.78


def estimate_unit_count(nra_m2: float) -> int:
    avg_unit_size = 1.9
    if nra_m2 <= 0:
        return 0
    return int(nra_m2 / avg_unit_size)


def calculate_conversion_capex(gba_m2: float) -> float:
    capex_per_m2 = 500
    return round(gba_m2 * capex_per_m2, 2)


def calculate_opex(annual_revenue: float) -> float:
    return round(annual_revenue * 0.30, 2)


def safe_divide(a: float, b: float) -> Optional[float]:
    if not b:
        return None
    return a / b


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
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Backwards-compatible economics calculator.

    Supports BOTH call styles:

    1. New dictionary style:
       calculate_economics(extracted)

    2. Old keyword style:
       calculate_economics(gba_m2=..., asking_price=..., asking_rent_month=...)

    This prevents worker/main.py crashes when older pipeline code passes
    keyword arguments.
    """

    data: Dict[str, Any] = dict(extracted or {})

    if gba_m2 is not None:
        data["gba_m2"] = gba_m2

    if neighbourhood is not None:
        data["neighbourhood"] = neighbourhood

    if asking_price is not None:
        data["asking_price"] = asking_price

    if asking_rent_month is not None:
        data["asking_rent_month"] = asking_rent_month

    if rent_per_m2 is not None:
        data["rent_per_m2"] = rent_per_m2

    if price_per_m2_nra is not None:
        data["price_per_m2_nra"] = price_per_m2_nra

    gba = _safe_float(data.get("gba_m2"), 0.0)
    district = str(data.get("neighbourhood") or data.get("district") or "")
    purchase_price = _safe_float(data.get("asking_price"), 0.0)
    monthly_rent = _safe_float(data.get("asking_rent_month"), 0.0)

    storage_revenue_per_m2_month = _safe_float(
        data.get("price_per_m2_nra"),
        get_storage_revenue(district),
    )

    occupancy_rate = 0.90

    efficiency = (
        _safe_float(nra_efficiency, 0.0)
        if nra_efficiency is not None
        else _safe_float(data.get("nra_efficiency"), 0.0)
    )

    if efficiency <= 0:
        efficiency = calculate_nra_efficiency(gba)

    nra_m2 = round(gba * efficiency, 2)

    estimated_units = estimate_unit_count(nra_m2)

    monthly_revenue = round(
        nra_m2 * storage_revenue_per_m2_month * occupancy_rate,
        2,
    )

    annual_revenue = round(monthly_revenue * 12, 2)

    annual_opex = calculate_opex(annual_revenue)

    conversion_capex = calculate_conversion_capex(gba)

    if monthly_rent > 0:
        model_type = "lease"
        annual_rent = round(monthly_rent * 12, 2)
        total_investment = conversion_capex
    else:
        model_type = "freehold"
        annual_rent = 0
        total_investment = purchase_price + conversion_capex

    ebitda = round(
        annual_revenue - annual_opex - annual_rent,
        2,
    )

    margin = round(safe_divide(ebitda, annual_revenue) or 0, 4)

    ebitda_yield = (
        round(safe_divide(ebitda, purchase_price) or 0, 4)
        if purchase_price > 0
        else None
    )

    true_ebitda_yield = (
        round(safe_divide(ebitda, total_investment) or 0, 4)
        if total_investment > 0
        else None
    )

    if ebitda > 0:
        payback_years = (
            round(purchase_price / ebitda, 2)
            if purchase_price > 0
            else None
        )
        true_payback_years = round(total_investment / ebitda, 2)
    else:
        payback_years = None
        true_payback_years = None

    result = EconomicsResult(
        model_type=model_type,
        storage_revenue_per_m2_month=storage_revenue_per_m2_month,
        occupancy_rate=occupancy_rate,
        nra_efficiency=efficiency,
        nra_m2=nra_m2,
        estimated_units=estimated_units,
        monthly_revenue=monthly_revenue,
        annual_revenue=annual_revenue,
        annual_rent=annual_rent,
        annual_opex=annual_opex,
        ebitda=ebitda,
        margin=margin,
        asking_price=purchase_price,
        conversion_capex=conversion_capex,
        total_investment=total_investment,
        ebitda_yield=ebitda_yield,
        true_ebitda_yield=true_ebitda_yield,
        payback_years=payback_years,
        true_payback_years=true_payback_years,
    )

    return result.__dict__