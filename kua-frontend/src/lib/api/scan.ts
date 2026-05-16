import { api } from "./client";
import type {
  AnalysisResult,
  AutoScanFilters,
  ScanResponse,
} from "./types";

export const scanApi = {
  /** Auto-build the Idealista search URL from filters and run a batch scan. */
  auto: (filters: AutoScanFilters) =>
    api<ScanResponse>(`/scan/idealista/auto`, {
      method: "POST",
      body: filters,
    }),

  /** Run a batch scan against a fully-formed Idealista search URL. */
  url: (params: {
    search_url: string;
    limit?: number;
    generate_excel?: boolean;
    filters_used?: Record<string, unknown>;
  }) =>
    api<ScanResponse>(`/scan/idealista`, {
      method: "POST",
      body: params,
    }),

  /** Analyse a single listing from URL or raw text. */
  analyse: (payload: { url?: string; text?: string; raw_text?: string }) =>
    api<AnalysisResult>(`/analyse`, {
      method: "POST",
      body: payload,
    }),
};
