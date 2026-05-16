"use client";

import {
  Activity,
  BadgeCheck,
  Coins,
  Flame,
  Gauge,
  Layers,
  ShieldX,
  Timer,
} from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { KpiWidget } from "@/components/dashboard/kpi-widget";
import { SystemActivity } from "@/components/dashboard/system-activity";
import { AcquisitionRadar } from "@/components/dashboard/acquisition-radar";
import { DealTable } from "@/components/dashboard/deal-table";
import { KpiGridSkeleton } from "@/components/common/loading-skeleton";
import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/common/status-pill";

import { useApprovedDeals, useTopDeals } from "@/hooks/use-deals";
import { usePortfolioKpis } from "@/hooks/use-kpis";
import Link from "next/link";

export default function CommandPage() {
  const kpis = usePortfolioKpis();
  const top = useTopDeals(8);
  const approved = useApprovedDeals(10);

  const radarPoints = (top.data ?? []).slice(0, 12).map((d, i) => ({
    id: d.id,
    angle: (i / 12) * 360,
    radius: Math.min(1, Math.max(0.2, (Number(d.score) || 0) / 100)),
    tone: (d.deal_status === "approved_candidate"
      ? "core"
      : d.deal_status === "rejected"
      ? "reject"
      : "review") as "core" | "review" | "reject",
  }));

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="OPS · COMMAND SURFACE"
        title="Acquisitions Command"
        subtitle="Live portfolio telemetry, AI underwriting throughput, and approved-deal pipeline."
        rightSlot={
          <>
            <StatusPill label="LIVE · BARCELONA" color="#7CFAB3" />
            <Link href="/scan">
              <Button variant="tactical" size="sm">
                <Flame className="h-3.5 w-3.5" /> Initiate Scan
              </Button>
            </Link>
          </>
        }
      />

      {kpis.loading ? (
        <KpiGridSkeleton count={4} />
      ) : (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          <KpiWidget
            label="Total Scanned"
            value={kpis.totalScanned}
            icon={Layers}
            index={0}
            spark={[3, 5, 4, 6, 8, 7, 9, 11]}
          />
          <KpiWidget
            label="Approved Deals"
            value={kpis.approvedCount}
            icon={BadgeCheck}
            glow="neon"
            index={1}
            spark={[1, 2, 2, 3, 4, 5, 6, 7]}
          />
          <KpiWidget
            label="Rejected Deals"
            value={kpis.rejectedCount}
            icon={ShieldX}
            glow="rose"
            index={2}
            spark={[5, 4, 6, 5, 7, 6, 8, 7]}
          />
          <KpiWidget
            label="Investment Volume"
            value={kpis.totalInvestmentVolume}
            icon={Coins}
            index={3}
            format={(n) =>
              n >= 1_000_000
                ? `€${(n / 1_000_000).toFixed(2)}M`
                : `€${(n / 1_000).toFixed(0)}k`
            }
            spark={[3, 4, 6, 7, 9, 11, 13, 14]}
          />
        </div>
      )}

      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <KpiWidget
          label="Approval Rate"
          value={Math.round(kpis.approvalRate * 1000) / 10}
          icon={Gauge}
          suffix="%"
          decimals={1}
          index={0}
        />
        <KpiWidget
          label="Manual Review"
          value={kpis.manualReviewCount}
          icon={Activity}
          index={1}
        />
        <KpiWidget
          label="Avg True Yield"
          value={(kpis.avgEbitdaYield ?? 0) * 100}
          icon={Gauge}
          suffix="%"
          decimals={2}
          index={2}
        />
        <KpiWidget
          label="Avg Payback"
          value={kpis.avgPaybackYears ?? 0}
          icon={Timer}
          suffix=" yrs"
          decimals={1}
          index={3}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr_1fr]">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground">
              Top Approved Pipeline
            </h2>
            <Link
              href="/pipeline"
              className="font-mono text-[10px] uppercase tracking-widest text-primary hover:underline"
            >
              VIEW PIPELINE →
            </Link>
          </div>
          <DealTable deals={(approved.data ?? []).slice(0, 8)} />
        </div>
        <AcquisitionRadar points={radarPoints} scanned={kpis.totalScanned} />
        <SystemActivity />
      </div>
    </div>
  );
}
