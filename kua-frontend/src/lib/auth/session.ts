import "server-only";

import { cookies } from "next/headers";
import bcrypt from "bcryptjs";
import { authConfig, SESSION_COOKIE } from "./config";
import { signSession, verifySession } from "./jwt";
import type { AuthSessionUser } from "@/lib/api/types";

const isProd = process.env.NODE_ENV === "production";

export async function getSession(): Promise<AuthSessionUser | null> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  const payload = await verifySession(token);
  if (!payload) return null;

  return {
    username: String(payload.sub),
    displayName: String(payload.name),
    clearance: String(payload.clr),
    issuedAt: Number(payload.iat ?? 0),
    expiresAt: Number(payload.exp ?? 0),
  };
}

export async function requireSession() {
  const session = await getSession();
  if (!session) throw new Error("UNAUTHORIZED");
  return session;
}

export async function createLoginSession(input: {
  username: string;
  displayName: string;
  clearance: string;
}) {
  const { token, expiresAt } = await signSession(input);
  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: isProd,
    sameSite: "lax",
    path: "/",
    expires: new Date(expiresAt * 1000),
  });
}

export async function destroySession() {
  const store = await cookies();
  store.set(SESSION_COOKIE, "", {
    httpOnly: true,
    secure: isProd,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}

/**
 * Validate credentials against the configured operator account.
 *
 * In production swap this for a call to your FastAPI auth router (see
 * `kua_auth_example.py` in the backend). The interface stays the same.
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
