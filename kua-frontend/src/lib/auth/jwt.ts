import { SignJWT, jwtVerify, type JWTPayload } from "jose";
import { authConfig } from "./config";

/**
 * Session token payload — kept tiny on purpose.
 * Sensitive data lives server-side, never inside the cookie.
 */
export interface SessionPayload extends JWTPayload {
  sub: string;            // username
  name: string;           // display name
  clr: string;            // clearance level
}

const ISSUER = "kua.frontend";
const AUDIENCE = "kua.operators";

let cachedKey: Uint8Array | null = null;
function getKey() {
  if (!cachedKey) cachedKey = new TextEncoder().encode(authConfig.secret);
  return cachedKey;
}

export async function signSession(payload: {
  username: string;
  displayName: string;
  clearance: string;
}) {
  const now = Math.floor(Date.now() / 1000);
  const exp = now + authConfig.ttlSeconds;

  const token = await new SignJWT({
    sub: payload.username,
    name: payload.displayName,
    clr: payload.clearance,
  } satisfies SessionPayload)
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setIssuer(ISSUER)
    .setAudience(AUDIENCE)
    .setIssuedAt(now)
    .setExpirationTime(exp)
    .sign(getKey());

  return { token, issuedAt: now, expiresAt: exp };
}

export async function verifySession(token: string): Promise<SessionPayload | null> {
  try {
    const { payload } = await jwtVerify(token, getKey(), {
      issuer: ISSUER,
      audience: AUDIENCE,
    });
    return payload as SessionPayload;
  } catch {
    return null;
  }
}
