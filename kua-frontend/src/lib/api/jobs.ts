import { api } from "./client";
import type {
  AutoScanFilters,
  ScanJobResponse,
  ScanJobStarted,
} from "./types";

/**
 * Async scan job API client.
 * Long-running scans run on the worker — the frontend just kicks them off
 * and polls for state.
 */
export const jobsApi = {
  /** Start auto scan — returns job_id immediately. 60s timeout for cold worker enqueue. */
  startAutoScan: (filters: AutoScanFilters) =>
    api<ScanJobStarted>(`/scan/idealista/auto`, {
      method: "POST",
      body: filters,
      timeoutMs: 60_000,
    }),

  /** Start URL-based scan — returns job_id immediately. */
  startUrlScan: (params: {
    search_url: string;
    limit?: number;
    generate_excel?: boolean;
    filters_used?: Record<string, unknown>;
  }) =>
    api<ScanJobStarted>(`/scan/idealista`, {
      method: "POST",
      body: params,
      timeoutMs: 60_000,
    }),

  /** Poll job state. Short timeout because the worker only reads Supabase. */
  getJob: (jobId: string) =>
    api<ScanJobResponse>(`/jobs/${jobId}`, {
      method: "GET",
      timeoutMs: 20_000,
      dedupe: false,
    }),

  /** List recent jobs. */
  listJobs: (limit = 20, status?: string) =>
    api<{ success: boolean; jobs: ScanJobResponse["job"][] }>(`/jobs`, {
      method: "GET",
      query: { limit, status },
      timeoutMs: 15_000,
    }),

  /** Cancel a running job. Best-effort — server marks status=cancelled. */
  cancelJob: (jobId: string) =>
    api<{ success: boolean; job: ScanJobResponse["job"] }>(
      `/jobs/${jobId}/cancel`,
      { method: "POST", timeoutMs: 15_000 }
    ),

  /** Re-queue a failed/timeout job for the worker to retry. */
  retryJob: (jobId: string) =>
    api<{ success: boolean; job: ScanJobResponse["job"]; message: string }>(
      `/jobs/${jobId}/retry`,
      { method: "POST", timeoutMs: 15_000 }
    ),

  /** Sweep stuck jobs (admin). */
  cleanup: () =>
    api<{ success: boolean; recovered: number }>(`/jobs/cleanup`, {
      method: "POST",
      timeoutMs: 30_000,
    }),
};
