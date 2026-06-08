"""
Investment-committee memo generator for the laundry vertical.

The memo is deterministic so that re-running the analysis on the same inputs
always produces the same prose. Optionally, the caller may ask for an LLM
rewrite pass — facts are preserved, only the prose is polished.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List


def _eur(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"€{float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _pct_already(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _bullets(items: List[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None"


def generate_ic_memo(
    *,
    property_data: Dict[str, Any],
    economics: Dict[str, Any],
    score: Dict[str, Any],
    due_diligence: Dict[str, Any],
) -> str:
    """Render the full IC memo in Markdown."""
    address = property_data.get("address") or "Address unavailable"
    city = property_data.get("city") or "—"
    neighbourhood = property_data.get("neighbourhood") or "—"
    listing_url = property_data.get("listing_url") or "—"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sub = score.get("auto_scores", {})
    confidence = score.get("confidence", {})

    sections = [
        f"# K.U.A. LAUNDRY — INVESTMENT COMMITTEE MEMO",
        "",
        f"**Property:** {address}, {neighbourhood}, {city}  ",
        f"**Source:** {listing_url}  ",
        f"**Generated:** {now}  ",
        f"**Vertical:** Laundry Acquisition Engine  ",
        "",
        "---",
        "",
        "## 1. Recommendation",
        "",
        f"**Score:** {score.get('score')} / 100",
        f"**Verdict:** {score.get('verdict')}",
        f"**Classification:** {score.get('classification')}",
        f"**Deal Status:** {score.get('deal_status')}",
        f"**Confidence:** {confidence.get('band', 'medium').upper()} "
        f"({confidence.get('pct', '—')}%, {confidence.get('fields_present', 0)} critical fields present)",
        "",
        "## 2. Financial Snapshot",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Acquisition Type | {economics.get('acquisition_type', '—').upper()} |",
        f"| Floor Area | {economics.get('floor_area_m2')} m² |",
        f"| Washer × Dryer | {economics.get('washer_count')} × {economics.get('dryer_count')} |",
        f"| Total Investment | {_eur(economics.get('total_investment_eur'))} |",
        f"| Acquisition Cost | {_eur(economics.get('acquisition_cost_eur'))} |",
        f"| Capex (machines + fit-out) | {_eur(economics.get('capex_eur'))} |",
        f"| Annual Rent | {_eur(economics.get('rent_cost_eur'))} |",
        f"| Expected Revenue (Y1) | {_eur(economics.get('expected_revenue_eur'))} |",
        f"| Steady-State Revenue | {_eur(economics.get('steady_state_revenue_eur'))} |",
        f"| Annual Opex | {_eur(economics.get('annual_opex_eur'))} |",
        f"| EBITDA | {_eur(economics.get('ebitda_eur'))} |",
        f"| Operating Margin | {_pct(economics.get('operating_margin'))} |",
        f"| Yield (EBITDA / Total Investment) | {_pct(economics.get('yield_pct'))} |",
        f"| IRR (10y, indicative) | {_pct_already(economics.get('irr_estimate_pct'))} |",
        f"| Payback | {economics.get('payback_years', '—')} years |",
        f"| Break-Even Revenue | {_eur(economics.get('break_even_revenue_eur'))} |",
        "",
        "## 3. Cost Stack (Capex)",
        "",
        f"| Line Item | Value |",
        f"|-----------|-------|",
        f"| Construction / Fit-out | {_eur(economics.get('construction_cost_eur'))} |",
        f"| Machine Investment | {_eur(economics.get('machine_capex_eur'))} |",
        f"| Ancillary Equipment | {_eur(economics.get('ancillary_capex_eur'))} |",
        f"| Electrical Upgrades | {_eur(economics.get('electrical_upgrades_eur'))} |",
        f"| Plumbing Upgrades | {_eur(economics.get('plumbing_upgrades_eur'))} |",
        f"| Ventilation | {_eur(economics.get('ventilation_eur'))} |",
        f"| Drainage | {_eur(economics.get('drainage_upgrades_eur'))} |",
        f"| Gas Connection | {_eur(economics.get('gas_connection_eur'))} |",
        f"| Water Supply | {_eur(economics.get('water_supply_eur'))} |",
        f"| Signage / Branding | {_eur(economics.get('signage_branding_eur'))} |",
        f"| Legal | {_eur(economics.get('legal_costs_eur'))} |",
        f"| Licensing | {_eur(economics.get('licensing_eur'))} |",
        f"| Initial Marketing | {_eur(economics.get('initial_marketing_eur'))} |",
        f"| Initial Staff Setup | {_eur(economics.get('initial_staff_setup_eur'))} |",
        f"| Working Capital | {_eur(economics.get('working_capital_eur'))} |",
        "",
        "## 4. Operating Cost Stack",
        "",
        f"| Line Item | Value |",
        f"|-----------|-------|",
        f"| Electricity | {_eur(economics.get('electricity_cost_eur'))} |",
        f"| Gas | {_eur(economics.get('gas_cost_eur'))} |",
        f"| Water | {_eur(economics.get('water_cost_eur'))} |",
        f"| Cleaning | {_eur(economics.get('cleaning_cost_eur'))} |",
        f"| Supplies | {_eur(economics.get('supplies_cost_eur'))} |",
        f"| Payroll | {_eur(economics.get('payroll_cost_eur'))} |",
        f"| Maintenance | {_eur(economics.get('maintenance_cost_eur'))} |",
        f"| Insurance | {_eur(economics.get('insurance_cost_eur'))} |",
        f"| Internet | {_eur(economics.get('internet_cost_eur'))} |",
        f"| Waste | {_eur(economics.get('waste_cost_eur'))} |",
        f"| Rent | {_eur(economics.get('rent_cost_eur'))} |",
        "",
        "## 5. Location Diagnostic",
        "",
        f"- Location score: **{sub.get('location_score', '—')} / 100**",
        f"- Competition score: **{sub.get('competition_score', '—')} / 100**",
        f"- Physical fit score: **{sub.get('physical_fit_score', '—')} / 100**",
        f"- Economics score: **{sub.get('economics_score', '—')} / 100**",
        f"- Risk score: **{sub.get('risk_score', '—')} / 100**",
        "",
        "**Drivers:**",
        f"- Economics: {', '.join(score.get('drivers', {}).get('economics', [])) or '—'}",
        f"- Physical: {', '.join(score.get('drivers', {}).get('physical', [])) or '—'}",
        f"- Risk: {', '.join(score.get('drivers', {}).get('risk', [])) or '—'}",
        "",
        "## 6. SWOT",
        "",
        "**Strengths**",
        _bullets(due_diligence.get("strengths", [])),
        "",
        "**Weaknesses**",
        _bullets(due_diligence.get("weaknesses", [])),
        "",
        "**Opportunities**",
        _bullets(due_diligence.get("opportunities", [])),
        "",
        "**Threats**",
        _bullets(due_diligence.get("threats", [])),
        "",
        "## 7. Red Flags",
        "",
        _bullets(due_diligence.get("red_flags", [])),
        "",
        "## 8. Required Verification",
        "",
        _bullets(due_diligence.get("required_verification", [])),
        "",
        "## 9. Recommended Next Steps",
        "",
        _bullets(due_diligence.get("next_steps", [])),
        "",
        "---",
        "_All figures generated by the K.U.A. Laundry Acquisition Engine._",
        "_Assumptions versioned as_ `" + str(economics.get("assumptions_version", "1.0.0")) + "`",
    ]
    return "\n".join(sections)


def generate_rejection_note(
    *,
    property_data: Dict[str, Any],
    economics: Dict[str, Any],
    score: Dict[str, Any],
) -> str:
    """Short note kept on rejected deals so they can still be skimmed."""
    return f"""
# LAUNDRY REJECTION SUMMARY

Property: {property_data.get("address") or "—"}, {property_data.get("city") or "—"}
Verdict: {score.get("verdict")}
Score: {score.get("score")}/100
Classification: {score.get("classification")}

Key metrics:
- Floor area: {economics.get("floor_area_m2")} m²
- Total investment: {_eur(economics.get("total_investment_eur"))}
- EBITDA: {_eur(economics.get("ebitda_eur"))}
- Yield: {_pct(economics.get("yield_pct"))}
- Payback: {economics.get("payback_years")} years

This opportunity does not meet the laundry acquisition threshold. It remains
saved in the rejected history and can be restored or re-scored at any time.
""".strip()


async def llm_polish(memo_markdown: str) -> str:
    """Optional second-pass that rewrites prose with the configured LLM provider."""
    from app.ai.providers.base import get_provider  # lazy — avoids LLM dep at import time

    provider = get_provider()
    system = (
        "You are an institutional investment-memo editor for a laundromat "
        "acquisition fund. Preserve every number and bullet exactly. Improve "
        "clarity and tone only. Output valid Markdown."
    )
    try:
        return await provider.complete(system, memo_markdown)
    except Exception:
        return memo_markdown
