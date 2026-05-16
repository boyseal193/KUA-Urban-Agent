import { NextResponse } from "next/server";
import { z } from "zod";
import {
  createLoginSession,
  validateCredentials,
} from "@/lib/auth/session";
import { authConfig } from "@/lib/auth/config";

export const runtime = "nodejs";

const schema = z.object({
  username: z.string().min(1).max(64),
  password: z.string().min(1).max(256),
});

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid credentials payload" },
      { status: 400 }
    );
  }

  // If a FastAPI auth endpoint is configured, prefer it (production path).
  if (authConfig.backendAuthUrl) {
    const r = await fetch(authConfig.backendAuthUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed.data),
      cache: "no-store",
    });
    if (!r.ok) {
      return NextResponse.json(
        { error: "Authentication failed" },
        { status: 401 }
      );
    }
    const data = (await r.json()) as {
      username: string;
      displayName: string;
      clearance: string;
    };
    await createLoginSession({
      username: data.username,
      displayName: data.displayName ?? data.username,
      clearance: data.clearance ?? "tier-1",
    });
    return NextResponse.json({ ok: true });
  }

  // Local fallback: environment-configured operator
  const session = await validateCredentials(parsed.data);
  if (!session) {
    return NextResponse.json(
      { error: "Invalid username or password" },
      { status: 401 }
    );
  }

  await createLoginSession({
    username: session.username,
    displayName: session.displayName,
    clearance: session.clearance,
  });

  return NextResponse.json({ ok: true, user: session });
}
