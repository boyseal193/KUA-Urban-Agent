/**
 * Universal authenticated reverse-proxy → FastAPI backend.
 *
 * The browser hits /api/proxy/<anything> with the user's session cookie.
 * This handler:
 *   1. validates the session JWT
 *   2. rewrites the URL to BACKEND_API_URL + /<anything>
 *   3. forwards method, headers, body, query
 *   4. injects the operator identity + (if present) the FastAPI bearer token
 *   5. streams the response back
 *
 * Why we do this:
 *   • the FastAPI URL stays server-side (security + portability)
 *   • CORS goes away — the browser only talks to the Next.js origin
 *   • auth becomes uniform regardless of where FastAPI runs
 *   • we can layer rate-limits / audit logging in a single place
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

async function forward(
  req: Request,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const session = await getSessionInternal();
  if (!session) {
    return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
  }

  const base = authConfig.backendApiUrl;
  if (!base) {
    return NextResponse.json(
      { error: "BACKEND_API_URL not configured" },
      { status: 500 }
    );
  }

  const { path } = await ctx.params;
  const url = new URL(req.url);
  const target =
    base +
    "/" +
    path.map(encodeURIComponent).join("/") +
    url.search;

  const headers = new Headers();
  for (const [k, v] of req.headers.entries()) {
    if (!HOP_HEADERS.has(k.toLowerCase())) headers.set(k, v);
  }
  headers.set("x-kua-user", session.username);
  headers.set("x-kua-clearance", session.clearance);
  if (session.backendToken && !headers.has("authorization")) {
    headers.set("Authorization", `Bearer ${session.backendToken}`);
  }

  const method = req.method.toUpperCase();
  const init: RequestInit = {
    method,
    headers,
    body:
      method === "GET" || method === "HEAD"
        ? undefined
        : await req.arrayBuffer(),
    redirect: "manual",
    cache: "no-store",
  };

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (err) {
    console.error("[proxy] upstream error", err);
    return NextResponse.json(
      { error: "Upstream service unreachable" },
      { status: 502 }
    );
  }

  const responseHeaders = new Headers();
  for (const [k, v] of upstream.headers.entries()) {
    if (!HOP_HEADERS.has(k.toLowerCase())) responseHeaders.set(k, v);
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
