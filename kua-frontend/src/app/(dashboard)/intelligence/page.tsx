"use client";

import { BrainCircuit } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { StatusPill } from "@/components/common/status-pill";

import { ScoreDistributionChart } from "@/components/dashboard/score-distribution-chart";
import { DistrictBarChart } from "@/components/dashboard/district-bar-chart";
import { VerdictRadialChart } from "@/components/dashboard/verdict-radial-chart";
import { SystemActivity } from "@/components/dashboard/system-activity";

import { usePortfolioKpis } from "@/hooks/use-kpis";

export default function IntelligencePage() {
  const { allDeals } = usePortfolioKpis();

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="OPS · INTELLIGENCE"
        title="Portfolio Intelligence"
        subtitle="Cross-portfolio analytics: scoring distribution, district concentration, verdict mix."
        rightSlot={
          <>
            <StatusPill label="MODEL · gpt-5" color="#9C7BFF" />
            <StatusPill label="LIVE" color="#7CFAB3" />
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="panel p-5 lg:col-span-2">
          <header className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">
              Score Distribution
            </h3>
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {allDeals.length} deals
            </span>
          </header>
          <ScoreDistributionChart deals={allDeals} />
        </div>
        <div className="panel p-5">
          <header className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">
              Verdict Mix
            </h3>
            <BrainCircuit className="h-3.5 w-3.5 text-primary" />
          </header>
          <VerdictRadialChart deals={allDeals} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <div className="panel p-5">
          <header className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">
              District Concentration (top 10)
            </h3>
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              colour = avg score
            </span>
          </header>
          <DistrictBarChart deals={allDeals} />
        </div>
        <SystemActivity />
      </div>
    </div>
  );
}
