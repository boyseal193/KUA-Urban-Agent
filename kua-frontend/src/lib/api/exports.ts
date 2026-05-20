/**
 * Scan export API client.
 *
 * Unlike `api()` which assumes JSON, downloads need raw binary streaming
 * to a Blob with a sane timeout and abort handling. We hit the same
 * `/api/proxy/*` reverse-proxy so the session cookie + bearer flow stays
 * uniform, and we surface errors via the same {@link ApiError} class.
 */

import { ApiError, type ApiErrorPayload, formatApiErrorMessage, api } from "./client";

export type ExportFormat = "excel" | "csv" | "json" | "memo" | "zip";

export interface ExportArtifact {
  format: ExportFormat;
  status: string;
  size_bytes: number;
  file_name: string | null;
  mime_type: string | null;
  download_count: number;
  created_at: string | null;
  updated_at: string | null;
  url: string;
}

export interface ExportsListResponse {
  success: boolean;
  job_id: string;
  exports: ExportArtifact[];
}

export const EXPORT_FORMAT_META: Record<
  ExportFormat,
  { label: string; description: string }
> = {
  excel: {
    label: "Excel workbook",
    description: "4-sheet underwriting workbook (.xlsx)",
  },
  csv: {
    label: "CSV",
    description: "Flat property pipeline (.csv)",
  },
  json: {
    label: "JSON",
    description: "Raw structured export (.json)",
  },
  memo: {
    label: "IC memo",
    description: "Concatenated investment memos (.md)",
  },
  zip: {
    label: "Full package",
    description: "Everything bundled (.zip)",
  },
};

const DEFAULT_EXPORT_TIMEOUT_MS = 180_000; // 3 minutes — large scans may take a while

function inferFilename(headers: Headers, fallback: string): string {
  const disposition = headers.get("Content-Disposition") || "";
  const m = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(disposition);
  if (m && m[1]) {
    try {
      return decodeURIComponent(m[1].replace(/^"+|"+$/g, ""));
    } catch {
      return m[1].replace(/^"+|"+$/g, "");
    }
  }
  return fallback;
}

async function parseErrorPayload(res: Response): Promise<ApiErrorPayload | null> {
  try {
    const text = await res.text();
    if (!text) return null;
    return JSON.parse(text) as ApiErrorPayload;
  } catch {
    return null;
  }
}

/**
 * Download an export artifact and trigger a browser save dialog.
 *
 * Returns the {@link Blob} and final filename in case the caller wants to
 * do something more sophisticated (e.g. preview in-page).
 */
export async function downloadExport(
  jobId: string,
  format: ExportFormat,
  opts: { signal?: AbortSignal; timeoutMs?: number; openInsteadOfDownload?: boolean } = {}
): Promise<{ blob: Blob; filename: string }> {
  if (!jobId) {
    throw new ApiError("Missing job id", 400, null);
  }

  const timeoutMs = opts.timeoutMs ?? DEFAULT_EXPORT_TIMEOUT_MS;
  const controller = new AbortController();
  if (opts.signal) {
    if (opts.signal.aborted) controller.abort(opts.signal.reason);
    else opts.signal.addEventListener("abort", () => controller.abort(opts.signal!.reason));
  }
  const timer =
    timeoutMs > 0
      ? setTimeout(
          () => controller.abort(new DOMException("timeout", "TimeoutError")),
          timeoutMs
        )
      : null;

  let res: Response;
  try {
    res = await fetch(`/api/proxy/exports/${encodeURIComponent(jobId)}/${format}`, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (err) {
    if (timer) clearTimeout(timer);
    const aborted = (err as Error)?.name === "AbortError";
    const isTimeout =
      aborted &&
      (controller.signal.reason as Error | undefined)?.name === "TimeoutError";
    if (aborted && !isTimeout) {
      throw new ApiError("Download cancelled", 0, null, { aborted: true });
    }
    if (isTimeout) {
      throw new ApiError(
        `Export download timed out after ${Math.round(timeoutMs / 1000)}s`,
        504,
        null,
        { timeout: true }
      );
    }
    throw new ApiError("Network error during export download", 0, null, {
      network: true,
    });
  }
  if (timer) clearTimeout(timer);

  if (res.status === 401) {
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      const next = encodeURIComponent(
        window.location.pathname + window.location.search
      );
      window.location.assign(`/login?next=${next}`);
    }
    throw new ApiError("UNAUTHORIZED", 401, null);
  }

  if (!res.ok) {
    const payload = await parseErrorPayload(res);
    const message = formatApiErrorMessage(payload, res.status, res.statusText);
    throw new ApiError(message, res.status, payload);
  }

  const blob = await res.blob();
  const filename = inferFilename(res.headers, `kua-scan-${jobId.slice(0, 8)}.${format}`);

  if (!opts.openInsteadOfDownload && typeof window !== "undefined") {
    const url = URL.createObjectURL(blob);
    try {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } finally {
      // Defer revoke so Safari has time to flush the navigation.
      setTimeout(() => URL.revokeObjectURL(url), 4_000);
    }
  }

  return { blob, filename };
}

/** List which export artifacts are available for a job. */
export function listExports(jobId: string) {
  return api<ExportsListResponse>(`/exports/${encodeURIComponent(jobId)}`, {
    method: "GET",
    timeoutMs: 15_000,
  });
}

/** Force a fresh regeneration of all 5 export formats. */
export function regenerateExports(jobId: string) {
  return api<{ success: boolean; job_id: string; outcome: Record<ExportFormat, boolean> }>(
    `/exports/${encodeURIComponent(jobId)}/regenerate`,
    {
      method: "POST",
      timeoutMs: 180_000,
    }
  );
}
