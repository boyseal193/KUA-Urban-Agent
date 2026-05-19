/**
 * GET /api/auth/session
 *
 * Returns the public session object for the current operator (or null).
 * Never includes the backend bearer token — that stays inside the JWT cookie.
 */
import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const user = await getSession();
  return NextResponse.json(
    { authenticated: Boolean(user), user: user ?? null },
    { headers: { "Cache-Control": "no-store, private" } }
  );
}
