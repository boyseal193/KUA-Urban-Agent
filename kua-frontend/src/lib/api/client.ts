/**
 * K.U.A. universal fetch client.
 *
 * The browser does NOT call FastAPI directly. Every browser fetch goes to
 * `/api/proxy/*` which is implemented as a Next.js Route Handler that:
 *   1. Validates the session cookie via `getSession()`
 *   2. Forwards the request to `BACKEND_API_URL` (server-only env var)
 *   3. Returns the JSON / stream back to the browser
 *
 * This means:
 *   • the backend URL is never leaked to the browser
 *   • CORS becomes a non-issue
 *   • the same auth model works whether FastAPI lives on Render, Railway,
 *     Fly, a private VPC, or right next door on the same host
 */

export type FetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
};

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
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

/**
 * Public client used inside React components and hooks.
 * Hits the Next.js proxy at `/api/proxy/*` which then talks to FastAPI.
 */
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

  if (!res.ok) {
    const message =
      (data && typeof data === "object" && "error" in (data as any)
        ? String((data as any).error)
        : null) ?? res.statusText;
    throw new ApiError(message || "Request failed", res.status, data);
  }

  return data as T;
}

/**
 * Server-only fetch used inside Route Handlers / Server Components.
 * Talks directly to the FastAPI backend over the private network.
 */
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

  if (!res.ok) {
    throw new ApiError(
      `Backend responded ${res.status}`,
      res.status,
      data
    );
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
