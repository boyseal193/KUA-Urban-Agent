import type { LaundryProperty } from "@/lib/api";
import { money, num, pct, yearsLabel } from "@/lib/format";

export function displayPct(value: number | null | undefined, fallback = "—"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  const n = Number(value);
  return pct(n > 1 ? n / 100 : n, fallback);
}

export function monthlyFromAnnual(value: number | null | undefined): number | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  return Number(value) / 12;
}

export function machinesLabel(deal: LaundryProperty): string {
  const washers = deal.washer_count ?? 0;
  const dryers = deal.dryer_count ?? 0;
  if (!washers && !dryers) return "—";
  return `${washers}W · ${dryers}D`;
}

export function propertyTitle(deal: LaundryProperty): string {
  return deal.address || deal.neighbourhood || "Untitled property";
}

export function districtLabel(deal: LaundryProperty): string {
  return deal.matched_neighbourhood || deal.neighbourhood || "—";
}

export function aiSummary(deal: LaundryProperty): string {
  if (deal.ai_summary) return deal.ai_summary;
  if (deal.memo_preview) return deal.memo_preview.slice(0, 280);
  if (deal.verdict) return deal.verdict;
  return "Analysis pending — open the deal memo for the full underwriting narrative.";
}

export function pipelineMetrics(deal: LaundryProperty) {
  const revenue = deal.expected_revenue_eur ?? null;
  const ebitda = deal.ebitda_eur ?? null;
  return {
    area: deal.floor_area_m2 != null ? `${num(deal.floor_area_m2)} m²` : "—",
    machines: machinesLabel(deal),
    revenue: money(revenue),
    ebitda: money(ebitda),
    margin: displayPct(deal.operating_margin),
    payback: yearsLabel(deal.payback_years),
    monthlyRevenue: money(monthlyFromAnnual(revenue)),
    monthlyProfit: money(monthlyFromAnnual(ebitda)),
    annualEbitda: money(ebitda),
    investment: money(
      deal.total_investment_eur ??
        (deal.acquisition_type === "buy" ? deal.asking_price : null),
    ),
    roi: displayPct(deal.yield_pct),
    paybackYears: yearsLabel(deal.payback_years),
    locker: money(deal.locker_revenue_eur),
    vending: money(deal.vending_revenue_eur),
    upside: money(deal.upside_potential_eur),
    demand: deal.demand_score != null ? num(deal.demand_score, "—") : "—",
    competition: deal.competition_score != null ? num(deal.competition_score, "—") : "—",
    riskCount: deal.risk_count ?? deal.risk_flags?.length ?? 0,
    warningCount: deal.warning_count ?? 0,
    ddCount: deal.dd_items_count ?? 0,
  };
}
