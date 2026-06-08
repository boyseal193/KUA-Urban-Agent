"use client";

import Link from "next/link";
import {
  Activity,
  BadgeCheck,
  Flame,
  Gauge,
  Layers,
  ShieldX,
  Timer,
  WashingMachine,
} from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { KpiWidget } from "@/components/dashboard/kpi-widget";
import { LaundryDealCard } from "@/components/laundry/laundry-deal-card";
import { StatusPill } from "@/components/common/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/common/empty-state";
import {
  useLaundryApprovedDeals,
  useLaundryKpis,
  useLaundryManualReview,
  useLaundryTopDeals,
} from "@/hooks/use-laundry";

export default function LaundryDashboardPage() {
  const kpis = useLaundryKpis();
  const top = useLaundryTopDeals(8);
  const approved = useLaundryApprovedDeals(6);
  const review = useLaundryManualReview(6);

  const k = kpis.data;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="LAUNDRY · ACQUISITION ENGINE"
        title="Laundry Intelligence"
        subtitle="AI-driven discovery, underwriting and scoring of laundromat opportunities — buy, rent and conversion candidates."
        rightSlot={
          <>
            <StatusPill label="LIVE · LAUNDRY" color="#A78BFA" />
            <Link href="/laundry/scan">
              <Button variant="tactical" size="sm" className="bg-violet-500/10 text-violet-300 hover:bg-violet-500/20">
                <Flame className="h-3.5 w-3.5" /> Initiate Scan
              </Button>
            </Link>
          </>
        }
      />

      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <KpiWidget label="Scanned" value={k?.total_scanned ?? 0} icon={Layers} index={0} />
        <KpiWidget
          label="Approved"
          value={k?.approved_count ?? 0}
          icon={BadgeCheck}
          glow="neon"
          index={1}
        />
        <KpiWidget
          label="Manual Review"
          value={k?.manual_review_count ?? 0}
          icon={Activity}
          index={2}
        />
        <KpiWidget label="Rejected" value={k?.rejected_count ?? 0} icon={ShieldX} index={3} />
      </div>

      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <KpiWidget
          label="Approval Rate"
          value={(k?.approval_rate ?? 0) * 100}
          icon={Gauge}
          suffix="%"
          decimals={1}
          index={0}
        />
        <KpiWidget
          label="Avg Score"
          value={k?.avg_score ?? 0}
          icon={WashingMachine}
          decimals={1}
          index={1}
        />
        <KpiWidget
          label="Pipeline (Top)"
          value={(top.data ?? []).length}
          icon={BadgeCheck}
          index={2}
        />
        <KpiWidget
          label="Verdicts in Last Sweep"
          value={
            (approved.data ?? []).length +
            (review.data ?? []).length
          }
          icon={Timer}
          index={3}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top Approved</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(approved.data ?? []).length === 0 ? (
              <EmptyState
                title="No approved laundromats yet"
                description="Launch a scan to discover candidates."
                icon={BadgeCheck}
              />
            ) : (
              (approved.data ?? []).slice(0, 4).map((d, i) => (
                <LaundryDealCard key={d.id} deal={d} index={i} compact />
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Manual Review Queue</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(review.data ?? []).length === 0 ? (
              <EmptyState
                title="Manual review queue is empty"
                description="Properties that need operator inspection will appear here."
                icon={Activity}
              />
            ) : (
              (review.data ?? []).slice(0, 4).map((d, i) => (
                <LaundryDealCard key={d.id} deal={d} index={i} compact />
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
