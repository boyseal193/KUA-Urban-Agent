/**
 * GET /api/healthz
 *
 * Liveness probe for Railway. Intentionally has zero auth, zero side effects,
 * and zero imports from the auth subsystem so it cannot enter a restart loop
 * triggered by misconfiguration of AUTH_SECRET or BACKEND_API_URL.
 */
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(
    {
      ok: true,
      service: "kua-frontend",
      ts: new Date().toISOString(),
    },
    { headers: { "Cache-Control": "no-store" } }
  );
}

export async function HEAD() {
  return new NextResponse(null, {
    status: 200,
    headers: { "Cache-Control": "no-store" },
  });
}
