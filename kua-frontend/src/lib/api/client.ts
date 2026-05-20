/**
 * K.U.A. universal fetch client.
 *
 * Every browser fetch goes through this helper, which posts to
 * `/api/proxy/*` (a Next.js Route Handler). The proxy validates the
 * session cookie and forwards the request to FastAPI.
 *
 * Hardening:
 *   * AbortController-backed per-request timeout (DEFAULT_TIMEOUT_MS).
 *   * In-flight de-duplication for idempotent GETs.
 *   * Structured ApiError surfaced to callers (status, errorType,
 *     missingTables, retryable, setupRequired, requestId).
 *   * 401 → automatic hard navigation to /login so the dashboard never
 *     hangs on an expired session.
 */

export type FetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Disable cross-call de-duplication (e.g. for forced refetches). */
  dedupe?: boolean;
};

export interface ApiErrorPayload {
  success?: boolean;
  error_type?: string;
  message?: string;
  error?: string;
  detail?: unknown;
  missing_tables?: string[];
  setup_required?: boolean;
  retryable?: boolean;
  request_id?: string;
}

export class ApiError extends Error {
  status: number;
  payload: ApiErrorPayload | null;
  errorType?: string;
  missingTables?: string[];
  setupRequired: boolean;
  retryable: boolean;
  requestId?: string;
  isTimeout: boolean;
  isNetwork: boolean;
  isAborted: boolean;

  constructor(
    message: string,
    status: number,
    payload?: ApiErrorPayload | null,
    flags?: { timeout?: boolean; network?: boolean; aborted?: boolean }
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload ?? null;
    this.errorType = payload?.error_type;
    this.missingTables = payload?.missing_tables;
    this.setupRequired = Boolean(payload?.setup_required);
    this.retryable = Boolean(payload?.retryable);
    this.requestId = payload?.request_id;
    this.isTimeout = Boolean(flags?.timeout);
    this.isNetwork = Boolean(flags?.network);
    this.isAborted = Boolean(flags?.aborted);
  }
}

const DEFAULT_TIMEOUT_MS = 30_000;
const _inflight = new Map<string, Promise<unknown>>();

function buildQuery(query?: FetchOptions["query"]) {
  if (!query) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue;
    sp.append(k, String(v));
  }
  const str = sp.toString();
  return str ? `?${str}` : "";
}

function safeJson(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function formatApiErrorMessage(
  data: ApiErrorPayload | null,
  status: number,
  fallback = "Request failed"
): string {
  if (data?.error_type === "DatabaseSetupError") {
    const tables = data.missing_tables?.length
      ? data.missing_tables.join(", ")
      : "scan_jobs";
    return `Database setup incomplete: missing ${tables} table(s). Run jobs/schema.sql in Supabase SQL Editor.`;
  }

  const detail =
    typeof data?.detail === "string"
      ? data.detail
      : Array.isArray(data?.detail) && data!.detail!.length
      ? String(
          (data!.detail![0] as { msg?: unknown })?.msg ?? data!.detail![0]
        )
      : null;

  if (typeof data?.message === "string" && data.message.trim()) {
    return data.message;
  }
  if (typeof data?.error === "string" && data.error.trim()) {
    return data.error;
  }
  if (detail) return detail;

  if (status === 503) {
    return "Backend service unavailable. Check database setup and worker deployment.";
  }
  if (status === 502) {
    return "Backend reported a downstream failure. Retry shortly.";
  }
  if (status === 504) {
    return "Request timed out. Retry the action.";
  }
  if (status === 401) {
    return "Session expired. Please sign in again.";
  }

  return fallback;
}

function handleUnauthorized() {
  if (typeof window === "undefined") return;
  const here =
    window.location.pathname + window.location.search + window.location.hash;
  if (window.location.pathname === "/login") return;
  const next = encodeURIComponent(here || "/dashboard");
  window.location.assign(`/login?next=${next}`);
}

async function doFetch<T>(
  path: string,
  opts: FetchOptions
): Promise<T> {
  const url = `/api/proxy${path.startsWith("/") ? path : `/${path}`}${buildQuery(
    opts.query
  )}`;

  const headers = new Headers(opts.headers);
  if (!headers.has("Content-Type") && opts.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");

  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const userSignal = opts.signal;
  if (userSignal) {
    if (userSignal.aborted) controller.abort(userSignal.reason);
    else userSignal.addEventListener("abort", () => controller.abort(userSignal.reason));
  }
  const timeoutId =
    timeoutMs > 0
      ? setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), timeoutMs)
      : null;

  let res: Response;
  try {
    res = await fetch(url, {
      ...opts,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId);
    const aborted = (err as Error)?.name === "AbortError";
    const isTimeout = aborted && (controller.signal.reason as Error | undefined)?.name === "TimeoutError";
    if (aborted && !isTimeout) {
      throw new ApiError("Request cancelled", 0, null, { aborted: true });
    }
    if (isTimeout) {
      throw new ApiError(
        `Request timed out after ${Math.round(timeoutMs / 1000)}s`,
        504,
        null,
        { timeout: true }
      );
    }
    throw new ApiError("Network error: backend unreachable", 0, null, {
      network: true,
    });
  }
  if (timeoutId) clearTimeout(timeoutId);

  const text = await res.text().catch(() => "");
  const data = text ? safeJson(text) : null;
  const payload =
    data && typeof data === "object" ? (data as ApiErrorPayload) : null;

  if (res.status === 401) {
    handleUnauthorized();
    throw new ApiError("UNAUTHORIZED", 401, payload);
  }

  if (!res.ok) {
    const message = formatApiErrorMessage(payload, res.status, res.statusText);
    throw new ApiError(message, res.status, payload);
  }

  return data as T;
}

export async function api<T = unknown>(
  path: string,
  opts: FetchOptions = {}
): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();
  if (
    method === "GET" &&
    opts.dedupe !== false &&
    typeof window !== "undefined"
  ) {
    const key = `${method} ${path}${buildQuery(opts.query)}`;
    const existing = _inflight.get(key);
    if (existing) return existing as Promise<T>;
    const p = doFetch<T>(path, opts).finally(() => _inflight.delete(key));
    _inflight.set(key, p as Promise<unknown>);
    return p;
  }
  return doFetch<T>(path, opts);
}

/**
 * Direct server-side call (RSC, route handler) that bypasses the proxy.
 * Used very rarely — most server work should still hit /api/proxy so that
 * auth, logging, and timeout handling stay centralised.
 */
export async function serverApi<T = unknown>(
  path: string,
  opts: FetchOptions = {}
): Promise<T> {
  const base = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL;
  if (!base) {
    throw new ApiError(
      "BACKEND_API_URL is not configured on the server",
      500
    );
  }

  const url = `${base.replace(/\/$/, "")}${
    path.startsWith("/") ? path : `/${path}`
  }${buildQuery(opts.query)}`;

  const headers = new Headers(opts.headers);
  if (!headers.has("Content-Type") && opts.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");

  const controller = new AbortController();
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timeoutId =
    timeoutMs > 0
      ? setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), timeoutMs)
      : null;

  let res: Response;
  try {
    res = await fetch(url, {
      ...opts,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId);
    const aborted = (err as Error)?.name === "AbortError";
    const isTimeout = aborted && (controller.signal.reason as Error | undefined)?.name === "TimeoutError";
    throw new ApiError(
      isTimeout
        ? `Upstream timeout after ${Math.round(timeoutMs / 1000)}s`
        : "Upstream service unreachable",
      isTimeout ? 504 : 502,
      null,
      { timeout: isTimeout, network: !isTimeout }
    );
  }
  if (timeoutId) clearTimeout(timeoutId);

  const text = await res.text().catch(() => "");
  const data = text ? safeJson(text) : null;
  const payload =
    data && typeof data === "object" ? (data as ApiErrorPayload) : null;

  if (!res.ok) {
    const message = formatApiErrorMessage(
      payload,
      res.status,
      `Backend responded ${res.status}`
    );
    throw new ApiError(message, res.status, payload);
  }

  return data as T;
}
