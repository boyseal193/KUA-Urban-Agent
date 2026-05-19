/**
 * POST /api/auth/login
 *
 * Authenticates an operator. Strategy:
 *   1. If a FastAPI auth URL is configured (the production path), proxy the
 *      credentials there, capture the bearer token, mint a Next.js JWT
 *      session cookie, and return the public user object.
 *   2. Otherwise (dev/local), fall back to bcrypt-checking a local
 *      operator account configured via env vars.
 *
 * On success: 200 { ok: true, user }
 * On bad payload: 400 { error }
 * On bad credentials: 401 { error }
 * On upstream / config failure: 502 { error }
 */
import { NextResponse } from "next/server";
import { z } from "zod";
import {
  createLoginSession,
  validateCredentials,
} from "@/lib/auth/session";
import { authConfig } from "@/lib/auth/config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const LOGIN_TIMEOUT_MS = 15_000;

const schema = z.object({
  username: z.string().trim().min(1, "username required").max(64),
  password: z.string().min(1, "password required").max(256),
});

interface FastApiLoginResponse {
  success?: boolean;
  message?: string;
  username?: string;
  displayName?: string;
  display_name?: string;
  clearance?: string;
  access_token?: string;
  token_type?: string;
  detail?: unknown;
}

function toDisplayName(username: string): string {
  if (!username) return "Operator";
  return username.charAt(0).toUpperCase() + username.slice(1);
}

function extractDetail(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object") {
    const msg = (detail[0] as { msg?: unknown }).msg;
    if (typeof msg === "string") return msg;
  }
  const error = (data as { error?: unknown }).error;
  if (typeof error === "string") return error;
  const message = (data as { message?: unknown }).message;
  if (typeof message === "string") return message;
  return null;
}

export async function POST(req: Request) {
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    raw = {};
  }

  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid credentials payload" },
      { status: 400 }
    );
  }

  // ---- Production path: proxy to FastAPI ------------------------------------
  if (authConfig.backendAuthUrl) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), LOGIN_TIMEOUT_MS);

    let upstream: Response;
    try {
      upstream = await fetch(authConfig.backendAuthUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(parsed.data),
        cache: "no-store",
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timer);
      console.error("[auth/login] Backend unreachable:", err);
      return NextResponse.json(
        { error: "Authentication service unreachable" },
        { status: 502 }
      );
    }
    clearTimeout(timer);

    const text = await upstream.text();
    let data: FastApiLoginResponse | null = null;
    if (text) {
      try {
        data = JSON.parse(text) as FastApiLoginResponse;
      } catch {
        data = null;
      }
    }

    if (!upstream.ok) {
      const detail = extractDetail(data) ?? "Invalid username or password";
      // 401 if backend says so, 502 for anything else (5xx / weirdness)
      const status = upstream.status === 401 || upstream.status === 403 ? 401 : 502;
      return NextResponse.json({ error: detail }, { status });
    }

    const username =
      (data?.username && String(data.username)) || parsed.data.username;
    const displayName =
      (data?.displayName && String(data.displayName)) ||
      (data?.display_name && String(data.display_name)) ||
      toDisplayName(username);
    const clearance =
      (data?.clearance && String(data.clearance)) || "operator";
    const backendToken =
      typeof data?.access_token === "string" && data.access_token.length > 0
        ? data.access_token
        : undefined;

    const user = await createLoginSession({
      username,
      displayName,
      clearance,
      backendToken,
    });

    return NextResponse.json({ ok: true, user });
  }

  // ---- Fallback path: local bcrypt operator (dev / break-glass) -------------
  const session = await validateCredentials(parsed.data);
  if (!session) {
    return NextResponse.json(
      { error: "Invalid username or password" },
      { status: 401 }
    );
  }

  const user = await createLoginSession({
    username: session.username,
    displayName: session.displayName,
    clearance: session.clearance,
  });
  return NextResponse.json({ ok: true, user });
}
