"""Deterministic Markdown investment memo + rejection note generator.

No LLM dependency — kept pure so it always works in production.
"""
from __future__ import annotations

from typing import Any, Dict


def _fmt_eur(v) -> str:
    if v is None: return "—"
    try: return f"€{float(v):,.0f}"
    except (TypeError, ValueError): return str(v)


def _fmt_pct(v) -> str:
    if v is None: return "—"
    try: return f"{float(v) * 100:.1f}%" if abs(float(v)) <= 1 else f"{float(v):.1f}%"
    except (TypeError, ValueError): return str(v)


def _fmt_num(v) -> str:
    if v is None: return "—"
    try: return f"{float(v):,.1f}"
    except (TypeError, ValueError): return str(v)


def generate_ic_memo(*, extracted: Dict[str, Any], economics: Dict[str, Any],
                     scoring: Dict[str, Any], location: Dict[str, Any],
                     due_diligence: Dict[str, Any]) -> str:
    address = extracted.get("address") or "(address unknown)"
    city = extracted.get("city") or location.get("city") or "Barcelona"
    acquisition_type = (extracted.get("acquisition_type") or economics.get("acquisition_type") or "rent").upper()
    floor_area = economics.get("floor_area_m2") or extracted.get("floor_area_m2") or 0
    preferred = scoring.get("preferred_market", {}) or {}

    md = []
    md.append(f"# INVESTMENT COMMITTEE — LAUNDROMAT OPPORTUNITY")
    md.append("")
    md.append(f"**Property:** {address}, {city}")
    md.append(f"**Acquisition:** {acquisition_type}")
    md.append(f"**Floor area:** {_fmt_num(floor_area)} m² ({economics.get('right_size_status', '—')})")
    md.append(f"**Verdict:** {scoring.get('verdict', '—')}  ·  **Score:** {scoring.get('score', 0)}/100  ·  **Class:** {scoring.get('classification', '—')}")
    if preferred.get("matched"):
        md.append(f"**Preferred market:** {preferred.get('matched')} ({preferred.get('reason')})")
    md.append("")

    md.append("## Executive summary")
    md.append("")
    if scoring.get("deal_status") == "approved_candidate":
        md.append(f"This opportunity scores **{scoring.get('score')}/100** and lands in the **approved candidate** band. ")
    elif scoring.get("deal_status") == "manual_review":
        md.append(f"This opportunity scores **{scoring.get('score')}/100** and requires **manual review**. ")
    else:
        md.append(f"This opportunity scores **{scoring.get('score')}/100** and is **rejected** by the engine. ")
    md.append(f"Year-1 revenue is projected at **{_fmt_eur(economics.get('expected_revenue_eur'))}** with **{_fmt_eur(economics.get('ebitda_eur'))}** EBITDA, "
              f"a **{_fmt_pct(economics.get('operating_margin'))}** operating margin, and a **{_fmt_num(economics.get('payback_years'))} year** payback.")
    md.append("")

    md.append("## Financial highlights")
    md.append("")
    md.append(f"- **Total investment:** {_fmt_eur(economics.get('total_investment_eur'))}")
    md.append(f"  - Acquisition: {_fmt_eur(economics.get('acquisition_cost_eur'))}")
    md.append(f"  - Capex (machines + fit-out): {_fmt_eur(economics.get('capex_eur'))}")
    md.append(f"  - Working capital + setup: {_fmt_eur((economics.get('working_capital_eur') or 0) + (economics.get('initial_staff_setup_eur') or 0))}")
    md.append(f"- **Expected revenue (Y1):** {_fmt_eur(economics.get('expected_revenue_eur'))}")
    md.append(f"  - Machine revenue: {_fmt_eur(economics.get('year1_revenue_eur'))}")
    md.append(f"  - In-store ancillary: {_fmt_eur(economics.get('in_store_ancillary_revenue_eur'))}")
    md.append(f"  - Secondary lines: {_fmt_eur(economics.get('secondary_revenue_eur'))}")
    md.append(f"- **OPEX (annual):** {_fmt_eur(economics.get('annual_opex_eur'))}")
    md.append(f"- **EBITDA:** {_fmt_eur(economics.get('ebitda_eur'))}  ·  **Margin:** {_fmt_pct(economics.get('operating_margin'))}")
    md.append(f"- **Yield:** {_fmt_pct(economics.get('yield_pct'))}  ·  **Payback:** {_fmt_num(economics.get('payback_years'))} y  ·  **IRR (approx):** {_fmt_pct(economics.get('irr_estimate_pct'))}")
    md.append(f"- **Break-even:** {_fmt_eur(economics.get('break_even_revenue_eur'))} / yr")
    md.append("")

    md.append("## Physical configuration")
    md.append("")
    md.append(f"- Washers: **{economics.get('washer_count', 0)}** "
              f"(std {economics.get('standard_washer_count', 0)} / large {economics.get('large_washer_count', 0)})")
    md.append(f"- Dryers: **{economics.get('dryer_count', 0)}** "
              f"(std {economics.get('standard_dryer_count', 0)} / stacking {economics.get('stacking_dryer_count', 0)})")
    md.append(f"- Folding stations: {economics.get('folding_stations', 0)}  ·  Seating: {economics.get('customer_seating_units', 0)}")
    md.append(f"- Vending — detergent: {economics.get('detergent_vending_units', 0)} · snack: {economics.get('snack_vending_units', 0)} · drink: {economics.get('drink_vending_units', 0)}")
    md.append(f"- Payment kiosks: {economics.get('payment_kiosks', 0)}")
    md.append("")

    md.append("## Location analysis")
    md.append("")
    md.append(f"- Population density: {_fmt_num(location.get('population_density_per_km2'))} /km²")
    md.append(f"- Household income: {_fmt_eur(location.get('household_income_eur'))}")
    md.append(f"- Apartment density: {_fmt_pct(location.get('apartment_density_pct'))}")
    md.append(f"- Competitors within 1km: {location.get('competitors_within_1km', '—')}  ·  Nearby laundromats (500m): {location.get('nearby_laundromats_within_500m', '—')}")
    md.append(f"- Walkability: {location.get('walkability_score_0_100', '—')}  ·  Night safety: {location.get('night_safety_0_100', '—')}")
    md.append(f"- Hotels (500m): {location.get('hotels_within_500m', '—')}  ·  Students (1km): {location.get('students_within_1km', '—')}  ·  Universities (2km): {location.get('universities_within_2km', '—')}")
    md.append("")

    swot = (due_diligence or {}).get("swot", {})
    md.append("## SWOT")
    md.append("")
    for label, key in [("Strengths", "strengths"), ("Weaknesses", "weaknesses"),
                       ("Opportunities", "opportunities"), ("Threats", "threats")]:
        md.append(f"### {label}")
        for item in swot.get(key, []) or []: md.append(f"- {item}")
        md.append("")

    md.append("## Risks & red flags")
    md.append("")
    for r in (due_diligence or {}).get("risks", []) or []: md.append(f"- {r}")
    for r in (due_diligence or {}).get("red_flags", []) or []: md.append(f"- **RED FLAG:** {r}")
    md.append("")

    md.append("## Due diligence checklist")
    md.append("")
    for item in (due_diligence or {}).get("due_diligence_checklist", []) or []: md.append(f"- [ ] {item}")
    md.append("")

    sens = (economics.get("sensitivity") or {}).get("scenarios") or []
    if sens:
        md.append("## Sensitivity (downside / base / upside)")
        md.append("")
        md.append("| Scenario | Revenue | OPEX | EBITDA | Payback |")
        md.append("|---|---|---|---|---|")
        for s in sens:
            md.append(f"| {s.get('label')} | {_fmt_eur(s.get('revenue_eur'))} | {_fmt_eur(s.get('opex_eur'))} | {_fmt_eur(s.get('ebitda_eur'))} | {_fmt_num(s.get('payback_years'))} y |")
        md.append("")

    md.append("## Recommendation")
    md.append("")
    if scoring.get("deal_status") == "approved_candidate":
        md.append("**Proceed.** Schedule site visit, validate utilities and lease terms, then advance to LOI.")
    elif scoring.get("deal_status") == "manual_review":
        md.append("**Investigate.** Resolve the missing or borderline metrics before approving. Pay particular attention to confidence drivers and right-size status.")
    else:
        md.append("**Pass.** Returns / fit / market do not clear our thresholds — re-evaluate only if material new information arrives.")
    md.append("")

    return "\n".join(md)


def generate_rejection_note(*, extracted: Dict[str, Any], economics: Dict[str, Any],
                             scoring: Dict[str, Any]) -> str:
    address = extracted.get("address") or "(address unknown)"
    return (
        f"# REJECTION NOTE\n\n"
        f"**Property:** {address}\n"
        f"**Score:** {scoring.get('score', 0)}/100  ·  **Classification:** {scoring.get('classification', '—')}\n"
        f"**EBITDA:** {_fmt_eur(economics.get('ebitda_eur'))}  ·  **Payback:** {_fmt_num(economics.get('payback_years'))} y\n\n"
        f"## Why rejected\n\n"
        + "\n".join(f"- {n}" for n in (scoring.get('notes') or [])) + "\n\n"
        f"## Drivers\n\n"
        + "\n".join(f"- {d}" for d in (scoring.get('drivers', {}).get('economics') or []))
    )
