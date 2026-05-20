"use client";

import * as React from "react";
import { Radar } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { ScanLauncher } from "@/components/scan/scan-launcher";
import { LiveScanFeed } from "@/components/scan/live-scan-feed";
import { ScanHistory } from "@/components/scan/scan-history";
import { StatusPill } from "@/components/common/status-pill";
import { ErrorBoundary } from "@/components/error-boundary";
import type { AnalysisResult, ScanResponse } from "@/lib/api/types";

export default function ScanPage() {
  const [liveResults, setLiveResults] = React.useState<AnalysisResult[]>([]);
  const [summary, setSummary] = React.useState<ScanResponse | null>(null);

  // Stable callbacks — passed to a child that wraps them in useEffect.
  // Without these, every render would create a new function reference,
  // forcing the child's useEffect to re-run and re-emit (root cause of
  // the historic React #185 maximum-update-depth crash).
  const handleLiveResults = React.useCallback((r: AnalysisResult[]) => {
    setLiveResults((prev) => (prev === r ? prev : r));
  }, []);
  const handleSummary = React.useCallback((s: ScanResponse | null) => {
    setSummary((prev) => (prev === s ? prev : s));
  }, []);

  const topDeals = React.useMemo(() => {
    if (summary?.top_deals?.length) return summary.top_deals;
    return liveResults.filter(
      (r) =>
        r?.deal_status === "approved_candidate" ||
        r?.deal_status === "manual_review"
    );
  }, [summary, liveResults]);

  const rejected = React.useMemo(() => {
    if (summary?.rejected_history?.length) return summary.rejected_history;
    return liveResults.filter(
      (r) => r?.deal_status === "rejected" || r?.success === false
    );
  }, [summary, liveResults]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="OPS · ACQUISITION SWEEP"
        title="Live Scan"
        subtitle="Launch an async Idealista sweep. The backend worker processes listings in the background while this page polls live pipeline state."
        rightSlot={<StatusPill label="ASYNC ENGINE" color="#38E1FF" />}
      />

      <ErrorBoundary>
        <ScanLauncher
          onLiveResults={handleLiveResults}
          onSummary={handleSummary}
        />
      </ErrorBoundary>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <ErrorBoundary>
          <LiveScanFeed
            results={topDeals}
            title="Approved + Manual Review · Live"
            emptyHint="Run a sweep — listings appear here as each completes."
          />
        </ErrorBoundary>
        <ErrorBoundary>
          <LiveScanFeed
            results={rejected}
            title="Rejected / Failed · Live"
            emptyHint="Failed or rejected listings surface here during the scan."
          />
        </ErrorBoundary>
      </div>

      <ErrorBoundary>
        <ScanHistory limit={8} />
      </ErrorBoundary>

      <div className="flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-4 py-3 backdrop-blur-xl">
        <Radar className="h-3.5 w-3.5 text-primary" />
        <p className="text-xs text-muted-foreground">
          {summary?.excel_export_generated ? (
            <>
              Underwriting workbook exported ·{" "}
              <span className="font-mono text-foreground">
                {summary.excel_export_path}
              </span>
            </>
          ) : (
            <>Scans run asynchronously — exports download below as soon as a scan completes.</>
          )}
        </p>
      </div>
    </div>
  );
}
