"use client";

/**
 * Global active-scan context.
 *
 * This sits above every dashboard page in the layout tree, which means:
 *   1. The polling loop and React-Query subscription survive route changes —
 *      navigating from /scan → /pipeline → /deals does NOT cancel the scan.
 *   2. The active job id is mirrored to ``localStorage`` so a full browser
 *      refresh / reload picks up exactly where the operator left off.
 *   3. Any page can render the current scan status by calling
 *      ``useActiveScan()`` — no prop drilling, no duplicate polling loops.
 *
 * The scan itself runs server-side on the worker (see jobs/worker.py) and
 * persists in Supabase, so the frontend is purely a viewer — closing the
 * tab does NOT cancel the scan. The cancel endpoint must be called
 * explicitly by the operator.
 */

import * as React from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { jobsApi } from "@/lib/api/jobs";
import { ApiError } from "@/lib/api/client";
import { dealKeys } from "@/hooks/use-deals";
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

const STORAGE_KEY = "kua.activeJobId";
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
    if (!l || (l as { deleted_at?: unknown }).deleted_at != null) continue;
    if (l.result && typeof l.result === "object") {
      out.push(l.result as AnalysisResult);
    }
  }
  return out;
}

function readStoredJobId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v && v.length > 4 ? v : null;
  } catch {
    return null;
  }
}

function writeStoredJobId(id: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* quota / privacy mode — ignored */
  }
}

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------
export interface ActiveScanContextValue {
  jobId: string | null;
  job: ScanJobRecord | null;
  phase: ScanPhase;
  progress: number;
  steps: ScanStepRecord[];
  logs: ScanLogRecord[];
  errors: ScanErrorRecord[];
  listings: ScanListingResult[];
  liveResults: AnalysisResult[];
  summary: ScanJobResponse["summary"] | null;
  isPolling: boolean;
  isStarting: boolean;
  startScan: (filters: AutoScanFilters) => Promise<{ job_id?: string } | void>;
  cancelScan: () => Promise<void>;
  retryScan: () => Promise<void>;
  reset: () => void;
  resumeAvailable: boolean;
  resume: (jobId: string) => void;
  error: Error | null;
  isResumed: boolean;
}

const ActiveScanContext = React.createContext<ActiveScanContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------
export function ActiveScanProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();

  // Read from localStorage synchronously on mount so a page reload
  // immediately resumes the polling loop (no flash of "no scan").
  const [jobId, setJobIdState] = React.useState<string | null>(null);
  const [isResumed, setIsResumed] = React.useState(false);

  // Hydration-safe read: only attempt to restore on the client AFTER mount.
  React.useEffect(() => {
    const stored = readStoredJobId();
    if (stored) {
      setJobIdState(stored);
      setIsResumed(true);
    }
  }, []);

  const setJobId = React.useCallback((id: string | null) => {
    setJobIdState(id);
    writeStoredJobId(id);
  }, []);

  const [phase, setPhase] = React.useState<ScanPhase>("idle");
  const [progress, setProgress] = React.useState(0);

  // ----- start mutation ----------------------------------------------------
  const startMutation = useMutation<
    Awaited<ReturnType<typeof jobsApi.startAutoScan>>,
    Error,
    AutoScanFilters
  >({
    mutationFn: (filters) => jobsApi.startAutoScan(filters),
    onSuccess: (res) => {
      if (res?.job_id) {
        setJobId(res.job_id);
        setIsResumed(false);
        setPhase("queued");
        setProgress(5);
      }
    },
    onError: () => {
      setPhase("error");
    },
  });

  // ----- polling query -----------------------------------------------------
  const jobQuery = useQuery<ScanJobResponse, Error>({
    queryKey: ["scan-job", jobId],
    queryFn: () => jobsApi.getJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.job?.status;
      if (!status) return POLL_MS;
      return TERMINAL.includes(status) ? false : POLL_MS;
    },
    // Don't cancel polling on window blur — we want background updates so a
    // returning operator sees the latest state instantly.
    refetchOnWindowFocus: true,
    retry: (failureCount, error) => {
      if (error instanceof ApiError) {
        // 404 = the stored job id no longer exists in Supabase. Clear it.
        if (error.status === 404) {
          setJobId(null);
          return false;
        }
        if (error.status === 401) return false;
        if (error.setupRequired) return false;
      }
      return failureCount < 5;
    },
    // Exponential backoff for the transient case.
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 15_000),
  });

  const queryData = jobQuery.data;
  const job = queryData?.job ?? null;

  // ----- derived collections (stable refs across identical polls) ----------
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
  const liveResults = React.useMemo<AnalysisResult[]>(
    () => listingResultsToAnalysis(listings) || (EMPTY_RESULTS as AnalysisResult[]),
    [listings]
  );

  // ----- phase + progress --------------------------------------------------
  const jobStatus = job?.status;
  const jobCurrentStep = job?.current_step ?? null;
  const jobProgressPct = job?.progress_pct ?? 0;
  React.useEffect(() => {
    if (!jobStatus) return;
    const nextProgress = jobProgressPct;
    const nextPhase = mapJobPhase(jobStatus, jobCurrentStep);
    setProgress((prev) => (prev === nextProgress ? prev : nextProgress));
    setPhase((prev) => (prev === nextPhase ? prev : nextPhase));
    if (TERMINAL.includes(jobStatus)) {
      // Once we hit a terminal state, invalidate deals queries so the
      // dashboard / pipeline / map pick up the new properties immediately.
      qc.invalidateQueries({ queryKey: dealKeys.all });
    }
  }, [jobStatus, jobCurrentStep, jobProgressPct, qc]);

  // Auto-clear the stored job id once the scan reaches a terminal state.
  // We keep the in-memory state so /scan can still render the final result,
  // but a future page reload won't try to resume a completed scan.
  const terminalCleanupRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!jobStatus || !jobId) return;
    if (!TERMINAL.includes(jobStatus)) return;
    if (terminalCleanupRef.current === jobId) return;
    terminalCleanupRef.current = jobId;
    writeStoredJobId(null);
  }, [jobStatus, jobId]);

  // ----- actions -----------------------------------------------------------
  const reset = React.useCallback(() => {
    setJobId(null);
    setPhase("idle");
    setProgress(0);
    setIsResumed(false);
    startMutation.reset();
  }, [setJobId, startMutation]);

  const cancelScan = React.useCallback(async () => {
    if (!jobId) return;
    try {
      await jobsApi.cancelJob(jobId);
    } finally {
      await jobQuery.refetch();
    }
  }, [jobId, jobQuery]);

  const retryScan = React.useCallback(async () => {
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
      console.error("[scan] retry failed", err);
      throw err;
    }
  }, [jobId, jobQuery, reset]);

  const resume = React.useCallback(
    (id: string) => {
      setJobId(id);
      setIsResumed(true);
    },
    [setJobId]
  );

  const isPolling =
    Boolean(jobId) &&
    !TERMINAL.includes((job?.status ?? "queued") as ScanJobStatus);

  const error: Error | null = (() => {
    if (startMutation.error) return startMutation.error;
    if (jobQuery.error) return jobQuery.error;
    if (job?.status === "failed" || job?.status === "timeout") {
      return new Error(job.error_message ?? "Scan failed");
    }
    return null;
  })();

  const value: ActiveScanContextValue = {
    jobId,
    job: job as ScanJobRecord | null,
    phase,
    progress,
    steps,
    logs,
    errors,
    listings,
    liveResults,
    summary,
    isPolling,
    isStarting: startMutation.isPending,
    startScan: startMutation.mutateAsync,
    cancelScan,
    retryScan,
    reset,
    resumeAvailable: Boolean(jobId) && !isPolling && phase !== "complete",
    resume,
    error,
    isResumed,
  };

  return (
    <ActiveScanContext.Provider value={value}>
      {children}
    </ActiveScanContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export function useActiveScan(): ActiveScanContextValue {
  const ctx = React.useContext(ActiveScanContext);
  if (!ctx) {
    throw new Error("useActiveScan must be used inside <ActiveScanProvider>");
  }
  return ctx;
}
