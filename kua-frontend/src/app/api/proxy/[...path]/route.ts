/**
 * Universal authenticated reverse-proxy → FastAPI backend.
 *
 * Browser → /api/proxy/<anything>?... → this handler:
 *   1. validates the session JWT (cookie)
 *   2. rewrites the URL to BACKEND_API_URL/<anything>?...
 *   3. forwards method, headers, body, query
 *   4. injects operator identity headers and (if present) the FastAPI bearer
 *   5. enforces a wall-clock timeout (default 60s; 600s for /scan/*)
 *   6. converts any non-2xx body to a structured JSON envelope so the
 *      browser never sees raw HTML or empty responses
 *
 * Why we do this:
 *   * the FastAPI URL stays server-side (security + portability)
 *   * CORS goes away — the browser only talks to the Next.js origin
 *   * auth becomes uniform regardless of where FastAPI runs
 *   * we get a single place to add timeouts, logging, and request IDs
 */
import { NextResponse } from "next/server";
import { getSessionInternal } from "@/lib/auth/session";
import { authConfig } from "@/lib/auth/config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  "accept-encoding",
]);

const DEFAULT_TIMEOUT_MS = 60_000;
const LONG_TIMEOUT_PREFIXES = ["scan/", "analyse"];
const LONG_TIMEOUT_MS = 600_000; // 10 min — enqueue path

function pickTimeout(path: string[]): number {
  const joined = path.join("/");
  for (const p of LONG_TIMEOUT_PREFIXES) {
    if (joined.startsWith(p)) return LONG_TIMEOUT_MS;
  }
  return DEFAULT_TIMEOUT_MS;
}

function randomId() {
  return (
    Math.random().toString(36).slice(2, 10) +
    Date.now().toString(36).slice(-4)
  );
}

async function forward(
  req: Request,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const requestId = req.headers.get("x-request-id") ?? randomId();
  const session = await getSessionInternal();
  if (!session) {
    return NextResponse.json(
      {
        success: false,
        error: "UNAUTHORIZED",
        error_type: "AuthError",
        message: "Sign in required",
        request_id: requestId,
      },
      { status: 401, headers: { "x-request-id": requestId } }
    );
  }

  const base = authConfig.backendApiUrl;
  if (!base) {
    return NextResponse.json(
      {
        success: false,
        error_type: "ConfigError",
        message:
          "BACKEND_API_URL is not configured on the Next.js server. Set NEXT_PUBLIC_API_URL in Railway → Variables.",
        request_id: requestId,
      },
      { status: 500, headers: { "x-request-id": requestId } }
    );
  }

  const { path } = await ctx.params;
  const url = new URL(req.url);
  const target =
    base.replace(/\/+$/, "") +
    "/" +
    path.map(encodeURIComponent).join("/") +
    url.search;

  const headers = new Headers();
  for (const [k, v] of req.headers.entries()) {
    if (!HOP_HEADERS.has(k.toLowerCase())) headers.set(k, v);
  }
  headers.set("x-kua-user", session.username);
  headers.set("x-kua-clearance", session.clearance);
  headers.set("x-request-id", requestId);
  if (session.backendToken && !headers.has("authorization")) {
    headers.set("Authorization", `Bearer ${session.backendToken}`);
  }

  const method = req.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD" ? undefined : await req.arrayBuffer();

  const controller = new AbortController();
  const timeoutMs = pickTimeout(path);
  const timer = setTimeout(
    () => controller.abort(new DOMException("timeout", "TimeoutError")),
    timeoutMs
  );

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timer);
    const isTimeout =
      (err as Error)?.name === "AbortError" &&
      (controller.signal.reason as Error | undefined)?.name === "TimeoutError";
    console.error("[proxy] upstream error", {
      target,
      requestId,
      timeout: isTimeout,
      err,
    });
    return NextResponse.json(
      {
        success: false,
        error_type: isTimeout ? "UpstreamTimeout" : "UpstreamUnreachable",
        message: isTimeout
          ? `Backend did not respond within ${Math.round(timeoutMs / 1000)}s.`
          : "Backend is unreachable. The FastAPI service may be restarting.",
        retryable: true,
        request_id: requestId,
      },
      {
        status: isTimeout ? 504 : 502,
        headers: { "x-request-id": requestId },
      }
    );
  }
  clearTimeout(timer);

  const responseHeaders = new Headers();
  for (const [k, v] of upstream.headers.entries()) {
    if (!HOP_HEADERS.has(k.toLowerCase())) responseHeaders.set(k, v);
  }
  responseHeaders.set("x-request-id", requestId);

  // Normalise non-2xx HTML/empty responses to JSON envelopes the client can parse.
  if (!upstream.ok) {
    const contentType = upstream.headers.get("content-type") ?? "";
    const text = await upstream.text().catch(() => "");
    if (!contentType.includes("application/json")) {
      return NextResponse.json(
        {
          success: false,
          error_type: `Upstream${upstream.status}`,
          message:
            text.slice(0, 300) ||
            `Backend responded with status ${upstream.status}`,
          request_id: requestId,
        },
        {
          status: upstream.status,
          headers: responseHeaders,
        }
      );
    }
    // JSON body — pass through but guarantee request_id is present.
    let parsed: Record<string, unknown> | null = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
    return NextResponse.json(
      { ...(parsed ?? {}), request_id: requestId },
      { status: upstream.status, headers: responseHeaders }
    );
  }

  return new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
export const OPTIONS = forward;
