"use client";

import * as React from "react";
import { Radar } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { ScanLauncher } from "@/components/scan/scan-launcher";
import { LiveScanFeed } from "@/components/scan/live-scan-feed";
import { StatusPill } from "@/components/common/status-pill";
import type { AnalysisResult, ScanResponse } from "@/lib/api/types";

export default function ScanPage() {
  const [liveResults, setLiveResults] = React.useState<AnalysisResult[]>([]);
  const [summary, setSummary] = React.useState<ScanResponse | null>(null);

  const topDeals = summary?.top_deals?.length
    ? summary.top_deals
    : liveResults.filter(
        (r) => r.deal_status === "approved_candidate" || r.deal_status === "manual_review"
      );

  const rejected = summary?.rejected_history?.length
    ? summary.rejected_history
    : liveResults.filter((r) => r.deal_status === "rejected" || r.success === false);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="OPS · ACQUISITION SWEEP"
        title="Live Scan"
        subtitle="Launch an async Idealista sweep. The backend worker processes listings in the background while this page polls live pipeline state."
        rightSlot={<StatusPill label="ASYNC ENGINE" color="#38E1FF" />}
      />

      <ScanLauncher
        onLiveResults={setLiveResults}
        onSummary={(s) => setSummary(s ?? null)}
      />

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <LiveScanFeed
          results={topDeals}
          title="Approved + Manual Review · Live"
          emptyHint="Run a sweep — listings appear here as each completes."
        />
        <LiveScanFeed
          results={rejected}
          title="Rejected / Failed · Live"
          emptyHint="Failed or rejected listings surface here during the scan."
        />
      </div>

      <div className="flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-4 py-3 backdrop-blur-xl">
        <Radar className="h-3.5 w-3.5 text-primary" />
        <p className="text-xs text-muted-foreground">
          {summary?.excel_export_generated ? (
            <>
              Excel underwriting workbook exported ·{" "}
              <span className="font-mono text-foreground">{summary.excel_export_path}</span>
            </>
          ) : (
            <>Scans run asynchronously — no frontend timeout. Worker must be deployed on Railway.</>
          )}
        </p>
      </div>
    </div>
  );
}
