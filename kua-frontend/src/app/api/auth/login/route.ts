/**
 * POST /api/auth/login
 *
 * Browser → this route → FastAPI /auth/login → JWT cookie issued here.
 *
 * Responses:
 *   200 { ok: true, user }                       success
 *   400 { error: "Invalid credentials payload" } bad request body
 *   401 { error: <upstream detail or default> }  bad credentials
 *   502 { error: <upstream detail or default> }  upstream / network failure
 *
 * Every response is structured JSON; the frontend reads `error` to render
 * the message in the login form.
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
      console.error(
        "[auth/login] FastAPI unreachable",
        { backendAuthUrl: authConfig.backendAuthUrl },
        err
      );
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
      const detail =
        extractDetail(data) ??
        (upstream.status === 401 || upstream.status === 403
          ? "Invalid username or password"
          : `Upstream error (${upstream.status})`);
      console.warn("[auth/login] upstream rejected", {
        status: upstream.status,
        detail,
      });
      const status =
        upstream.status === 401 || upstream.status === 403 ? 401 : 502;
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

    console.info("[auth/login] success", { username });
    return NextResponse.json({ ok: true, user });
  }

  // ---- Fallback path: local bcrypt operator (dev / break-glass) -------------
  console.warn(
    "[auth/login] No backendAuthUrl configured — using local bcrypt fallback. " +
      "Set NEXT_PUBLIC_API_URL in Railway → Variables."
  );
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
