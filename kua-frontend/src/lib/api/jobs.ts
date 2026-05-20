import { api } from "./client";
import type {
  AutoScanFilters,
  ScanJobResponse,
  ScanJobStarted,
} from "./types";

export const jobsApi = {
  /** Start async auto scan — returns job_id immediately. */
  startAutoScan: (filters: AutoScanFilters) =>
    api<ScanJobStarted>(`/scan/idealista/auto`, {
      method: "POST",
      body: filters,
    }),

  /** Poll job status, steps, logs, and incremental listing results. */
  getJob: (jobId: string) =>
    api<ScanJobResponse>(`/jobs/${jobId}`, {
      method: "GET",
    }),

  /** List recent scan jobs. */
  listJobs: (limit = 20) =>
    api<{ success: boolean; jobs: ScanJobResponse["job"][] }>(`/jobs`, {
      method: "GET",
      query: { limit },
    }),

  /** Cancel a running job. */
  cancelJob: (jobId: string) =>
    api<{ success: boolean; job: ScanJobResponse["job"] }>(
      `/jobs/${jobId}/cancel`,
      { method: "POST" }
    ),
};
