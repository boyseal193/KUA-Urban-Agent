import "server-only";

import { cookies } from "next/headers";
import bcrypt from "bcryptjs";
import { authConfig, SESSION_COOKIE, isProd } from "./config";
import { signSession, verifySession } from "./jwt";
import type { AuthSessionUser } from "@/lib/api/types";

/**
 * Server-side session helpers.
 *
 * These run in the Node.js runtime (route handlers, server components) and
 * have access to bcrypt, `next/headers` cookies(), etc. The Edge middleware
 * must NOT import from this file — it uses `verifySession` from ./jwt
 * directly.
 */

export interface SessionInternal extends AuthSessionUser {
  /** Backend bearer token (FastAPI access_token). */
  backendToken?: string;
}

function payloadToUser(payload: {
  sub: unknown;
  name?: unknown;
  clr?: unknown;
  iat?: unknown;
  exp?: unknown;
  bt?: unknown;
}): SessionInternal {
  return {
    username: String(payload.sub ?? ""),
    displayName: String(payload.name ?? payload.sub ?? ""),
    clearance: String(payload.clr ?? "operator"),
    issuedAt: Number(payload.iat ?? 0),
    expiresAt: Number(payload.exp ?? 0),
    backendToken:
      typeof payload.bt === "string" && payload.bt.length > 0
        ? payload.bt
        : undefined,
  };
}

/**
 * Returns the current session (for layouts, RSC, route handlers).
 * The returned object includes the backend token for SERVER-SIDE use only.
 */
export async function getSessionInternal(): Promise<SessionInternal | null> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  const payload = await verifySession(token);
  if (!payload) return null;
  return payloadToUser(payload);
}

/**
 * Public-facing session (no secrets). Safe to pass to client components.
 */
export async function getSession(): Promise<AuthSessionUser | null> {
  const session = await getSessionInternal();
  if (!session) return null;
  const { backendToken: _backendToken, ...publicUser } = session;
  void _backendToken;
  return publicUser;
}

export async function requireSession(): Promise<AuthSessionUser> {
  const session = await getSession();
  if (!session) throw new Error("UNAUTHORIZED");
  return session;
}

/** Convenience: return only the FastAPI bearer token, server-side only. */
export async function getBackendToken(): Promise<string | null> {
  const session = await getSessionInternal();
  return session?.backendToken ?? null;
}

export interface CreateLoginInput {
  username: string;
  displayName: string;
  clearance: string;
  backendToken?: string;
}

/**
 * Sign a new session JWT and set the HttpOnly cookie on the response.
 * MUST be called from a route handler / server action.
 */
export async function createLoginSession(
  input: CreateLoginInput
): Promise<AuthSessionUser> {
  const { token, issuedAt, expiresAt } = await signSession(input);
  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: isProd,
    sameSite: "lax",
    path: "/",
    expires: new Date(expiresAt * 1000),
  });
  return {
    username: input.username,
    displayName: input.displayName,
    clearance: input.clearance,
    issuedAt,
    expiresAt,
  };
}

export async function destroySession(): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, "", {
    httpOnly: true,
    secure: isProd,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
    expires: new Date(0),
  });
}

/**
 * Local break-glass credential check (DEV / fallback only).
 * In production the /api/auth/login route should always be configured to
 * proxy to FastAPI; this is only used when no backend URL is configured.
 */
export async function validateCredentials(input: {
  username: string;
  password: string;
}): Promise<AuthSessionUser | null> {
  const op = authConfig.operator;
  if (!op.username || !op.passwordHash) return null;
  if (input.username !== op.username) return null;

  const ok = await bcrypt.compare(input.password, op.passwordHash);
  if (!ok) return null;

  const now = Math.floor(Date.now() / 1000);
  return {
    username: op.username,
    displayName: op.displayName,
    clearance: op.clearance,
    issuedAt: now,
    expiresAt: now + authConfig.ttlSeconds,
  };
}
