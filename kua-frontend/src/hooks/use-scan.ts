"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { jobsApi } from "@/lib/api/jobs";
import { dealKeys } from "./use-deals";
import type {
  AnalysisResult,
  AutoScanFilters,
  ScanJobResponse,
  ScanJobStatus,
  ScanStepRecord,
} from "@/lib/api/types";

export type ScanPhase =
  | "idle"
  | "queued"
  | "running"
  | "scraping"
  | "analysing"
  | "scoring"
  | "exporting"
  | "complete"
  | "error"
  | "cancelled";

const TERMINAL: ScanJobStatus[] = [
  "success",
  "failed",
  "cancelled",
  "timeout",
];

const POLL_MS = 2000;

function mapJobPhase(status: ScanJobStatus, currentStep?: string | null): ScanPhase {
  if (status === "queued" || status === "pending") return "queued";
  if (status === "failed" || status === "timeout") return "error";
  if (status === "cancelled") return "cancelled";
  if (status === "success") return "complete";
  if (currentStep === "collect_listing_urls" || currentStep === "scrape_listing") return "scraping";
  if (
    currentStep === "extract_property_data" ||
    currentStep === "validate_extraction" ||
    currentStep === "calculate_economics"
  ) {
    return "analysing";
  }
  if (
    currentStep === "score_property" ||
    currentStep === "classify_deal" ||
    currentStep === "generate_memo" ||
    currentStep === "save_to_supabase"
  ) {
    return "scoring";
  }
  if (currentStep === "export_artifacts") return "exporting";
  return "running";
}

function listingResultsToAnalysis(listings: ScanJobResponse["listings"]): AnalysisResult[] {
  return listings
    .filter((l) => l.result && typeof l.result === "object")
    .map((l) => l.result as AnalysisResult);
}

export function useAutoScan() {
  const qc = useQueryClient();
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [phase, setPhase] = React.useState<ScanPhase>("idle");
  const [progress, setProgress] = React.useState(0);

  const startMutation = useMutation({
    mutationFn: (filters: AutoScanFilters) => jobsApi.startAutoScan(filters),
    onSuccess: (res) => {
      setJobId(res.job_id);
      setPhase("queued");
      setProgress(5);
    },
    onError: () => {
      setPhase("error");
    },
  });

  const jobQuery = useQuery({
    queryKey: ["scan-job", jobId],
    queryFn: () => jobsApi.getJob(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.job.status;
      if (!status) return POLL_MS;
      return TERMINAL.includes(status) ? false : POLL_MS;
    },
  });

  React.useEffect(() => {
    const job = jobQuery.data?.job;
    if (!job) return;
    setProgress(job.progress_pct ?? 0);
    setPhase(mapJobPhase(job.status, job.current_step));
    if (TERMINAL.includes(job.status)) {
      qc.invalidateQueries({ queryKey: dealKeys.all });
    }
  }, [jobQuery.data, qc]);

  const reset = React.useCallback(() => {
    setJobId(null);
    setPhase("idle");
    setProgress(0);
    startMutation.reset();
  }, [startMutation]);

  const cancel = React.useCallback(async () => {
    if (!jobId) return;
    await jobsApi.cancelJob(jobId);
    await jobQuery.refetch();
  }, [jobId, jobQuery]);

  const summary = jobQuery.data?.summary;
  const listings = jobQuery.data?.listings ?? [];
  const steps: ScanStepRecord[] = jobQuery.data?.steps ?? [];
  const logs = jobQuery.data?.logs ?? [];
  const errors = jobQuery.data?.errors ?? [];

  return {
    mutateAsync: startMutation.mutateAsync,
    isPending: startMutation.isPending || (Boolean(jobId) && !TERMINAL.includes(jobQuery.data?.job.status as ScanJobStatus)),
    isLoading: startMutation.isPending,
    isPolling: Boolean(jobId) && !TERMINAL.includes(jobQuery.data?.job.status as ScanJobStatus),
    error: startMutation.error ?? (jobQuery.data?.job.status === "failed" ? new Error(jobQuery.data.job.error_message ?? "Scan failed") : null),
    data: summary,
    job: jobQuery.data?.job ?? null,
    jobId,
    phase,
    progress,
    steps,
    logs,
    errors,
    liveResults: listingResultsToAnalysis(listings),
    reset,
    cancel,
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
