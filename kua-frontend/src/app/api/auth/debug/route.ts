/**
 * GET /api/auth/debug
 *
 * Diagnostic endpoint — returns the resolved backend URL, env source, and
 * runtime info. NEVER returns secrets or user data.
 *
 * Use this to confirm Railway env vars are loaded WITHOUT redeploying or
 * shelling into the container:
 *
 *   curl https://<frontend>.up.railway.app/api/auth/debug
 *
 * Public path — also added to middleware allowlist.
 */
import { NextResponse } from "next/server";
import { authConfig, authDebug } from "@/lib/auth/config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(
    {
      ok: true,
      service: "kua-frontend",
      ts: new Date().toISOString(),
      backendApiUrl: authConfig.backendApiUrl,
      backendAuthUrl: authConfig.backendAuthUrl,
      cookieName: authConfig.cookieName,
      ttlSeconds: authConfig.ttlSeconds,
      resolvedFrom: authDebug.resolvedFrom,
      hasAuthSecret: authDebug.hasAuthSecret,
      nodeEnv: authDebug.nodeEnv,
    },
    { headers: { "Cache-Control": "no-store" } }
  );
}
