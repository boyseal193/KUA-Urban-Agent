"use client";

/**
 * Compatibility shim for the legacy ``useAutoScan`` hook.
 *
 * The hook now delegates to the global ``ActiveScanProvider`` so the scan
 * survives route changes and full browser reloads (see
 * ``src/lib/contexts/active-scan-context.tsx``). The previously-exported
 * shape is preserved exactly so existing call sites (scan-launcher,
 * scan-progress) keep compiling.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useActiveScan, type ScanPhase } from "@/lib/contexts/active-scan-context";
import { ApiError } from "@/lib/api/client";
import { dealKeys } from "./use-deals";

export type { ScanPhase };

export function useAutoScan() {
  const scan = useActiveScan();

  const error: ApiError | Error | null = scan.error;

  return {
    // start
    mutateAsync: scan.startScan,
    isPending: scan.isStarting || scan.isPolling,
    isLoading: scan.isStarting,
    // poll
    isPolling: scan.isPolling,
    error,
    data: scan.summary,
    job: scan.job,
    jobId: scan.jobId,
    phase: scan.phase,
    progress: scan.progress,
    steps: scan.steps,
    logs: scan.logs,
    errors: scan.errors,
    listings: scan.listings,
    liveResults: scan.liveResults,
    // actions
    reset: scan.reset,
    cancel: scan.cancelScan,
    retry: scan.retryScan,
    // resume affordances (new)
    resume: scan.resume,
    isResumed: scan.isResumed,
    resumeAvailable: scan.resumeAvailable,
  };
}

export function useAnalyseSingle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { url?: string; raw_text?: string }) => {
      const { scanApi } = await import("@/lib/api/scan");
      return scanApi.analyse(payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: dealKeys.all });
    },
  });
}
