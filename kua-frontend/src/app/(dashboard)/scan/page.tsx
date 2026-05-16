"use client";

import { Radar } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { ScanLauncher } from "@/components/scan/scan-launcher";
import { LiveScanFeed } from "@/components/scan/live-scan-feed";
import { useAutoScan } from "@/hooks/use-scan";
import { StatusPill } from "@/components/common/status-pill";

export default function ScanPage() {
  const scan = useAutoScan();

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="OPS · ACQUISITION SWEEP"
        title="Live Scan"
        subtitle="Trigger a synchronous AI-powered Idealista sweep. Listings stream into the underwriting pipeline and surface in the live feed."
        rightSlot={<StatusPill label="ENGINE ARMED" color="#38E1FF" />}
      />

      <ScanLauncher />

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <LiveScanFeed
          results={scan.data?.top_deals ?? scan.data?.all_results ?? []}
          title="Approved + Manual Review · This Scan"
          emptyHint="Run a sweep to populate the live acquisition feed."
        />
        <LiveScanFeed
          results={scan.data?.rejected_history ?? []}
          title="Rejected Listings · This Scan"
          emptyHint="Rejected listings will surface here for transparency."
        />
      </div>

      <div className="flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-4 py-3 backdrop-blur-xl">
        <Radar className="h-3.5 w-3.5 text-primary" />
        <p className="text-xs text-muted-foreground">
          {scan.data?.excel_export_generated ? (
            <>
              Excel underwriting workbook exported · <span className="font-mono text-foreground">{scan.data?.excel_export_path}</span>
            </>
          ) : (
            <>
              Each scan optionally produces a full Excel underwriting workbook
              for offline review.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
