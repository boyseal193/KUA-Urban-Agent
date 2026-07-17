"use client";

import { motion } from "framer-motion";
import { TrendingUp } from "lucide-react";

import { money, num, pct, yearsLabel } from "@/lib/format";
import type { DealEconomics } from "@/lib/api/types";

interface EconomicsTableProps {
  economics?: Partial<DealEconomics> | null;
  className?: string;
}

export function EconomicsTable({ economics, className }: EconomicsTableProps) {
  const e = economics ?? {};

  const rows: { label: string; value: React.ReactNode; emphasis?: boolean }[] = [
    { label: "Model type", value: <span className="uppercase">{e.model_type ?? "—"}</span> },
    { label: "NRA", value: `${num(e.nra_m2)} m²` },
    { label: "NRA efficiency", value: pct(e.nra_efficiency) },
    { label: "Estimated units", value: e.estimated_units ?? "—" },
    { label: "Occupancy assumption", value: pct(e.occupancy_rate) },
    { label: "Storage revenue /m²/mo", value: money(e.storage_revenue_per_m2_month) },
    { label: "Monthly revenue", value: money(e.monthly_revenue) },
    { label: "Annual revenue", value: money(e.annual_revenue) },
    { label: "Annual OpEx", value: money(e.annual_opex) },
    { label: "Annual rent", value: money(e.annual_rent) },
    { label: "EBITDA (stabilised)", value: money(e.ebitda), emphasis: true },
    { label: "EBITDA margin", value: pct(e.margin), emphasis: true },
    { label: "Downside EBITDA", value: money(e.downside_ebitda_eur) },
    { label: "Severe downside EBITDA", value: money(e.severe_downside_ebitda_eur) },
    { label: "Price /m² (GBA)", value: money(e.price_per_m2_eur) },
    { label: "Transaction costs", value: money(e.acquisition_transaction_cost_eur) },
    { label: "Conversion CapEx", value: money(e.conversion_capex) },
    { label: "Working capital", value: money(e.working_capital_eur) },
    { label: "Total investment", value: money(e.total_investment), emphasis: true },
    { label: "Rent-to-revenue", value: pct(e.rent_to_revenue_pct) },
    { label: "EBITDA yield (price)", value: pct(e.ebitda_yield) },
    { label: "True EBITDA yield", value: pct(e.true_ebitda_yield), emphasis: true },
    { label: "Downside yield", value: pct(e.downside_yield_pct) },
    { label: "Payback (price only)", value: yearsLabel(e.payback_years) },
    { label: "True payback (incl. capex)", value: yearsLabel(e.true_payback_years), emphasis: true },
  ];

  return (
    <div className={`panel relative overflow-hidden ${className ?? ""}`}>
      <header className="flex items-center justify-between border-b border-border/60 px-5 py-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            Underwriting Economics
          </h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          INTERNAL · DO NOT DISTRIBUTE
        </span>
      </header>
      <div className="grid grid-cols-1 divide-y divide-border/40 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
        {chunk(rows, Math.ceil(rows.length / 2)).map((col, ci) => (
          <ul key={ci} className="divide-y divide-border/40">
            {col.map((r, i) => (
              <motion.li
                key={r.label}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.02 }}
                className="flex items-center justify-between px-5 py-2.5"
              >
                <span className="text-[11px] font-mono uppercase tracking-widest text-muted-foreground">
                  {r.label}
                </span>
                <span
                  className={`font-mono text-sm tabular-nums ${
                    r.emphasis ? "text-foreground font-semibold" : "text-foreground/80"
                  }`}
                >
                  {r.value}
                </span>
              </motion.li>
            ))}
          </ul>
        ))}
      </div>
    </div>
  );
}

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}
