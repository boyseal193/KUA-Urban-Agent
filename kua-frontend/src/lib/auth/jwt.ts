import { SignJWT, jwtVerify, type JWTPayload } from "jose";
import { authConfig } from "./config";

/**
 * Session token payload — kept intentionally tiny.
 * Sensitive data lives server-side; only routable identity goes in the cookie.
 */
export interface SessionPayload extends JWTPayload {
  /** Username (subject). */
  sub: string;
  /** Display name. */
  name: string;
  /** Clearance level. */
  clr: string;
  /** Optional backend bearer token (forwarded by the /api/proxy route). */
  bt?: string;
}

const ISSUER = "kua.frontend";
const AUDIENCE = "kua.operators";
const ALGORITHM = "HS256";

let cachedKey: Uint8Array | null = null;
function getKey(): Uint8Array {
  if (!cachedKey) cachedKey = new TextEncoder().encode(authConfig.secret);
  return cachedKey;
}

export interface SignInput {
  username: string;
  displayName: string;
  clearance: string;
  backendToken?: string;
}

export async function signSession(input: SignInput): Promise<{
  token: string;
  issuedAt: number;
  expiresAt: number;
}> {
  const now = Math.floor(Date.now() / 1000);
  const exp = now + authConfig.ttlSeconds;

  const payload: SessionPayload = {
    sub: input.username,
    name: input.displayName,
    clr: input.clearance,
  };
  if (input.backendToken) payload.bt = input.backendToken;

  const token = await new SignJWT(payload)
    .setProtectedHeader({ alg: ALGORITHM, typ: "JWT" })
    .setIssuer(ISSUER)
    .setAudience(AUDIENCE)
    .setIssuedAt(now)
    .setExpirationTime(exp)
    .sign(getKey());

  return { token, issuedAt: now, expiresAt: exp };
}

export async function verifySession(
  token: string
): Promise<SessionPayload | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, getKey(), {
      issuer: ISSUER,
      audience: AUDIENCE,
      algorithms: [ALGORITHM],
    });
    return payload as SessionPayload;
  } catch {
    return null;
  }
}
