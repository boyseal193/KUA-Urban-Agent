import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd


EXPORT_DIR = "exports"


def safe_get(data: Any, key: str, default=None):
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def money(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return value


def percent(value):
    if value is None:
        return None
    try:
        return round(float(value) * 100, 2)
    except Exception:
        return value


def flatten_result(result: Dict[str, Any]) -> Dict[str, Any]:
    extracted = safe_get(result, "extracted", {})
    economics = safe_get(result, "economics", {})
    score = safe_get(result, "score", {})
    auto_scores = safe_get(result, "auto_scores", {})

    return {
        "Property ID": safe_get(result, "property_id"),
        "Source URL": safe_get(result, "source_url") or safe_get(extracted, "listing_url") or safe_get(result, "url"),
        "Deal Status": safe_get(result, "deal_status"),
        "Score": safe_get(score, "score"),
        "Verdict": safe_get(score, "verdict"),
        "Classification": safe_get(score, "classification"),
        "Deal Killer": safe_get(score, "deal_killer"),

        "Address": safe_get(extracted, "address"),
        "City": safe_get(extracted, "city"),
        "Neighbourhood": safe_get(extracted, "neighbourhood"),

        "GBA m2": safe_get(extracted, "gba_m2"),
        "NRA m2": safe_get(economics, "nra_m2"),
        "NRA Efficiency %": percent(safe_get(economics, "nra_efficiency")),

        "Asking Price": money(safe_get(extracted, "asking_price")),
        "Asking Rent Month": money(safe_get(extracted, "asking_rent_month")),
        "Rent Per m2": money(safe_get(extracted, "rent_per_m2")),
        "Price Per m2 NRA": money(safe_get(extracted, "price_per_m2_nra")),

        "Ceiling Height": safe_get(extracted, "ceiling_height"),
        "Loading Access": safe_get(extracted, "loading_access"),
        "Access Type": safe_get(extracted, "access_type"),
        "Floor Level": safe_get(extracted, "floor_level"),
        "Building Type": safe_get(extracted, "building_type"),
        "Current Use": safe_get(extracted, "current_use"),

        "Model Type": safe_get(economics, "model_type"),
        "Estimated Units": safe_get(economics, "estimated_units"),
        "Monthly Revenue": money(safe_get(economics, "monthly_revenue")),
        "Annual Revenue": money(safe_get(economics, "annual_revenue")),
        "Annual Rent": money(safe_get(economics, "annual_rent")),
        "Annual Opex": money(safe_get(economics, "annual_opex")),
        "EBITDA": money(safe_get(economics, "ebitda")),
        "Margin %": percent(safe_get(economics, "margin")),
        "EBITDA Yield %": percent(safe_get(economics, "ebitda_yield")),
        "True EBITDA Yield %": percent(safe_get(economics, "true_ebitda_yield")),
        "Payback Years": safe_get(economics, "payback_years"),
        "True Payback Years": safe_get(economics, "true_payback_years"),
        "Conversion Capex": money(safe_get(economics, "conversion_capex")),
        "Total Investment": money(safe_get(economics, "total_investment")),

        "Location Score": safe_get(auto_scores, "location_score"),
        "Building Score": safe_get(auto_scores, "building_score"),
        "Economics Score": safe_get(auto_scores, "economics_score"),
        "Risk Score": safe_get(auto_scores, "risk_score"),
        "Strategic Fit Score": safe_get(auto_scores, "strategic_fit_score"),

        "Due Diligence Flags": " | ".join(safe_get(score, "due_diligence_flags", []) or []),
        "Description": safe_get(extracted, "description"),
        "Error": safe_get(result, "error"),
    }


def style_sheet(writer, sheet_name: str):
    worksheet = writer.sheets[sheet_name]

    worksheet.freeze_panes = "A2"

    for column_cells in worksheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter

        for cell in column_cells:
            try:
                if cell.value is not None:
                    max_length = max(max_length, len(str(cell.value)))
            except Exception:
                pass

        worksheet.column_dimensions[column_letter].width = min(max_length + 2, 55)

    for cell in worksheet[1]:
        cell.font = cell.font.copy(bold=True)


def export_scan_to_excel(
    results: List[Dict[str, Any]],
    top_deals: Optional[List[Dict[str, Any]]] = None,
    manual_review: Optional[List[Dict[str, Any]]] = None,
    rejected_history: Optional[List[Dict[str, Any]]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
    filters_used: Optional[Dict[str, Any]] = None,
    search_url: Optional[str] = None,
    filename: Optional[str] = None,
):
    os.makedirs(EXPORT_DIR, exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trutrastero_scan_{timestamp}.xlsx"

    export_path = os.path.join(EXPORT_DIR, filename)

    results = results or []
    top_deals = top_deals or []
    manual_review = manual_review or []
    rejected_history = rejected_history or []
    errors = errors or []

    all_rows = [flatten_result(r) for r in results if isinstance(r, dict)]
    top_rows = [flatten_result(r) for r in top_deals if isinstance(r, dict)]
    manual_rows = [flatten_result(r) for r in manual_review if isinstance(r, dict)]
    rejected_rows = [flatten_result(r) for r in rejected_history if isinstance(r, dict)]
    error_rows = [flatten_result(r) for r in errors if isinstance(r, dict)]

    summary_df = pd.DataFrame({
        "Metric": [
            "Search URL",
            "Total Results",
            "Top Deals Count",
            "Manual Review Count",
            "Rejected Count",
            "Error Count",
            "Generated At",
        ],
        "Value": [
            search_url,
            len(results),
            len(top_deals),
            len(manual_review),
            len(rejected_history),
            len(errors),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ],
    })

    filters_df = pd.DataFrame(
        [{"Filter": key, "Value": str(value)} for key, value in (filters_used or {}).items()]
    )

    with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        pd.DataFrame(top_rows).to_excel(writer, sheet_name="Top Deals", index=False)
        pd.DataFrame(manual_rows).to_excel(writer, sheet_name="Manual Review", index=False)
        pd.DataFrame(rejected_rows).to_excel(writer, sheet_name="Rejected", index=False)
        pd.DataFrame(error_rows).to_excel(writer, sheet_name="Errors", index=False)
        pd.DataFrame(all_rows).to_excel(writer, sheet_name="All Results", index=False)
        filters_df.to_excel(writer, sheet_name="Filters Used", index=False)

        for sheet_name in writer.sheets:
            style_sheet(writer, sheet_name)

    return export_path


def create_excel_report(
    results: List[Dict[str, Any]],
    top_deals: Optional[List[Dict[str, Any]]] = None,
    manual_review: Optional[List[Dict[str, Any]]] = None,
    rejected_history: Optional[List[Dict[str, Any]]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
    filters_used: Optional[Dict[str, Any]] = None,
    search_url: Optional[str] = None,
    filename: Optional[str] = None,
):
    return export_scan_to_excel(
        results=results,
        top_deals=top_deals,
        manual_review=manual_review,
        rejected_history=rejected_history,
        errors=errors,
        filters_used=filters_used,
        search_url=search_url,
        filename=filename,
    )