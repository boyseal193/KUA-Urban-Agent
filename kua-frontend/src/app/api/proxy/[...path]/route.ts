/**
 * Universal authenticated reverse-proxy → FastAPI backend.
 *
 * The browser hits /api/proxy/<anything> with the user's session cookie.
 * This handler:
 *   1. validates the session
 *   2. rewrites the URL to BACKEND_API_URL + /<anything>
 *   3. forwards method, headers, body, query
 *   4. streams the response back
 *
 * Why we do this:
 *   • the FastAPI URL stays server-side (security + portability)
 *   • CORS goes away — the browser only talks to the Next.js origin
 *   • auth becomes uniform regardless of where FastAPI runs
 *   • we can layer rate-limits / audit logging in a single place
 */
import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth/session";

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
]);

async function forward(
  req: Request,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
  }

  const base = process.env.BACKEND_API_URL;
  if (!base) {
    return NextResponse.json(
      { error: "BACKEND_API_URL not configured" },
      { status: 500 }
    );
  }

  const { path } = await ctx.params;
  const url = new URL(req.url);
  const target =
    base.replace(/\/$/, "") +
    "/" +
    path.map(encodeURIComponent).join("/") +
    url.search;

  const headers = new Headers();
  for (const [k, v] of req.headers.entries()) {
    if (!HOP_HEADERS.has(k.toLowerCase())) headers.set(k, v);
  }
  headers.set("x-kua-user", session.username);
  headers.set("x-kua-clearance", session.clearance);

  const init: RequestInit = {
    method: req.method,
    headers,
    body:
      req.method === "GET" || req.method === "HEAD"
        ? undefined
        : await req.arrayBuffer(),
    redirect: "manual",
    cache: "no-store",
  };

  const upstream = await fetch(target, init);

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
