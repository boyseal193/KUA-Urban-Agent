/**
 * POST /api/auth/logout
 *
 * Destroys the session cookie. Always returns 200 — logging out is idempotent
 * and must succeed even if the session is already expired/missing.
 */
import { NextResponse } from "next/server";
import { destroySession } from "@/lib/auth/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  await destroySession();
  return NextResponse.json({ ok: true });
}

// Some clients (curl debugging, link-style sign-out) issue GET — accept it.
export async function GET() {
  await destroySession();
  return NextResponse.json({ ok: true });
}
