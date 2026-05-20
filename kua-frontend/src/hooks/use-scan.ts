"use client";

import * as React from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { jobsApi } from "@/lib/api/jobs";
import { ApiError } from "@/lib/api/client";
import { dealKeys } from "./use-deals";
import type {
  AnalysisResult,
  AutoScanFilters,
  ScanErrorRecord,
  ScanJobRecord,
  ScanJobResponse,
  ScanJobStatus,
  ScanListingResult,
  ScanLogRecord,
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

const TERMINAL: ReadonlyArray<ScanJobStatus> = [
  "success",
  "failed",
  "cancelled",
  "timeout",
];

const POLL_MS = 2000;
const EMPTY_LISTINGS: ReadonlyArray<ScanListingResult> = Object.freeze([]);
const EMPTY_STEPS: ReadonlyArray<ScanStepRecord> = Object.freeze([]);
const EMPTY_LOGS: ReadonlyArray<ScanLogRecord> = Object.freeze([]);
const EMPTY_ERRORS: ReadonlyArray<ScanErrorRecord> = Object.freeze([]);
const EMPTY_RESULTS: ReadonlyArray<AnalysisResult> = Object.freeze([]);

function mapJobPhase(
  status: ScanJobStatus | undefined,
  currentStep?: string | null
): ScanPhase {
  if (!status) return "idle";
  if (status === "queued" || status === "pending") return "queued";
  if (status === "failed" || status === "timeout") return "error";
  if (status === "cancelled") return "cancelled";
  if (status === "success") return "complete";
  if (
    currentStep === "collect_listing_urls" ||
    currentStep === "scrape_listing"
  )
    return "scraping";
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

function listingResultsToAnalysis(
  listings: ReadonlyArray<ScanListingResult> | undefined
): AnalysisResult[] {
  if (!listings || listings.length === 0) return [];
  const out: AnalysisResult[] = [];
  for (const l of listings) {
    if (l && l.result && typeof l.result === "object") {
      out.push(l.result as AnalysisResult);
    }
  }
  return out;
}

/**
 * Async scan job hook.
 *
 * KEY DESIGN: every derived array (listings/steps/logs/errors/liveResults)
 * is memoized against the underlying react-query `data` reference. React-Query
 * uses structural sharing, so if the server returns identical data the
 * reference is stable and downstream useEffects DO NOT re-fire. This is what
 * killed the "Maximum update depth exceeded" (React #185) crash that occurred
 * when parent setState callbacks ran on every poll tick.
 */
export function useAutoScan() {
  const qc = useQueryClient();
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [phase, setPhase] = React.useState<ScanPhase>("idle");
  const [progress, setProgress] = React.useState(0);

  const startMutation = useMutation<
    Awaited<ReturnType<typeof jobsApi.startAutoScan>>,
    Error,
    AutoScanFilters
  >({
    mutationFn: (filters) => jobsApi.startAutoScan(filters),
    onSuccess: (res) => {
      if (res?.job_id) {
        setJobId(res.job_id);
        setPhase("queued");
        setProgress(5);
      }
    },
    onError: () => {
      setPhase("error");
    },
  });

  const jobQuery = useQuery<ScanJobResponse, Error>({
    queryKey: ["scan-job", jobId],
    queryFn: () => jobsApi.getJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.job?.status;
      if (!status) return POLL_MS;
      return TERMINAL.includes(status) ? false : POLL_MS;
    },
    retry: (failureCount, error) => {
      if (error instanceof ApiError) {
        if (error.status === 404 || error.status === 401) return false;
        if (error.setupRequired) return false;
      }
      return failureCount < 3;
    },
  });

  const queryData = jobQuery.data;
  const job = queryData?.job ?? null;

  // ----- Derived collections (referentially stable across identical polls).
  const listings = React.useMemo(
    () => (queryData?.listings ?? EMPTY_LISTINGS) as ScanListingResult[],
    [queryData?.listings]
  );
  const steps = React.useMemo(
    () => (queryData?.steps ?? EMPTY_STEPS) as ScanStepRecord[],
    [queryData?.steps]
  );
  const logs = React.useMemo(
    () => (queryData?.logs ?? EMPTY_LOGS) as ScanLogRecord[],
    [queryData?.logs]
  );
  const errors = React.useMemo(
    () => (queryData?.errors ?? EMPTY_ERRORS) as ScanErrorRecord[],
    [queryData?.errors]
  );
  const summary = queryData?.summary ?? null;
  const liveResults = React.useMemo(
    () => listingResultsToAnalysis(listings) || (EMPTY_RESULTS as AnalysisResult[]),
    [listings]
  );

  // ----- Phase + progress derived from job (single source of truth).
  const jobStatus = job?.status;
  const jobCurrentStep = job?.current_step ?? null;
  const jobProgressPct = job?.progress_pct ?? 0;
  const jobIdValue = job?.id;
  React.useEffect(() => {
    if (!jobStatus) return;
    const nextProgress = jobProgressPct;
    const nextPhase = mapJobPhase(jobStatus, jobCurrentStep);
    setProgress((prev) => (prev === nextProgress ? prev : nextProgress));
    setPhase((prev) => (prev === nextPhase ? prev : nextPhase));
    if (TERMINAL.includes(jobStatus)) {
      qc.invalidateQueries({ queryKey: dealKeys.all });
    }
  }, [jobStatus, jobCurrentStep, jobProgressPct, jobIdValue, qc]);

  // ----- Stable callbacks (memoized so consumers can use them in deps).
  const reset = React.useCallback(() => {
    setJobId(null);
    setPhase("idle");
    setProgress(0);
    startMutation.reset();
  }, [startMutation]);

  const cancel = React.useCallback(async () => {
    if (!jobId) return;
    try {
      await jobsApi.cancelJob(jobId);
    } finally {
      await jobQuery.refetch();
    }
  }, [jobId, jobQuery]);

  const retry = React.useCallback(async () => {
    if (!jobId) {
      reset();
      return;
    }
    try {
      await jobsApi.retryJob(jobId);
      setPhase("queued");
      setProgress(5);
      await jobQuery.refetch();
    } catch (err) {
      // Surface failure but do NOT loop — caller renders the error.
      console.error("[scan] retry failed", err);
      throw err;
    }
  }, [jobId, jobQuery, reset]);

  const isPolling =
    Boolean(jobId) &&
    !TERMINAL.includes((job?.status ?? "queued") as ScanJobStatus);

  const error: ApiError | Error | null = (() => {
    if (startMutation.error) return startMutation.error;
    if (jobQuery.error) return jobQuery.error;
    if (job?.status === "failed" || job?.status === "timeout") {
      return new Error(job.error_message ?? "Scan failed");
    }
    return null;
  })();

  return {
    mutateAsync: startMutation.mutateAsync,
    isPending: startMutation.isPending || isPolling,
    isLoading: startMutation.isPending,
    isPolling,
    error,
    data: summary,
    job: job as ScanJobRecord | null,
    jobId,
    phase,
    progress,
    steps,
    logs,
    errors,
    listings,
    liveResults,
    reset,
    cancel,
    retry,
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
