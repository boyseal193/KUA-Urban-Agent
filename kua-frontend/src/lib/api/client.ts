/**
 * K.U.A. universal fetch client.
 *
 * The browser does NOT call FastAPI directly. Every browser fetch goes to
 * `/api/proxy/*` which is implemented as a Next.js Route Handler that:
 *   1. Validates the session cookie via `getSession()`
 *   2. Forwards the request to `BACKEND_API_URL` (server-only env var)
 *   3. Returns the JSON / stream back to the browser
 */

export type FetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
};

export interface ApiErrorPayload {
  success?: boolean;
  error_type?: string;
  message?: string;
  error?: string;
  missing_tables?: string[];
  setup_required?: boolean;
  retryable?: boolean;
}

export class ApiError extends Error {
  status: number;
  payload: ApiErrorPayload | null;
  errorType?: string;
  missingTables?: string[];
  setupRequired: boolean;
  retryable: boolean;

  constructor(message: string, status: number, payload?: ApiErrorPayload | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload ?? null;
    this.errorType = payload?.error_type;
    this.missingTables = payload?.missing_tables;
    this.setupRequired = Boolean(payload?.setup_required);
    this.retryable = Boolean(payload?.retryable);
  }
}

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

  if (typeof data?.message === "string" && data.message.trim()) {
    return data.message;
  }

  if (typeof data?.error === "string" && data.error.trim()) {
    return data.error;
  }

  if (status === 503) {
    return "Backend service unavailable. Check database setup and worker deployment.";
  }

  return fallback;
}

export async function api<T = unknown>(
  path: string,
  opts: FetchOptions = {}
): Promise<T> {
  const url = `/api/proxy${path.startsWith("/") ? path : `/${path}`}${buildQuery(
    opts.query
  )}`;

  const headers = new Headers(opts.headers);
  if (!headers.has("Content-Type") && opts.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");

  const res = await fetch(url, {
    ...opts,
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    credentials: "include",
    cache: "no-store",
  });

  const text = await res.text();
  const data = text ? safeJson(text) : null;
  const payload =
    data && typeof data === "object" ? (data as ApiErrorPayload) : null;

  if (!res.ok) {
    const message = formatApiErrorMessage(payload, res.status, res.statusText);
    throw new ApiError(message, res.status, payload);
  }

  return data as T;
}

export async function serverApi<T = unknown>(
  path: string,
  opts: FetchOptions = {}
): Promise<T> {
  const base = process.env.BACKEND_API_URL;
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

  const res = await fetch(url, {
    ...opts,
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });

  const text = await res.text();
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

function safeJson(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
