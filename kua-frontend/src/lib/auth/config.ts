/**
 * Runtime auth configuration for K.U.A. frontend.
 *
 * Imported by both the Edge middleware and the Node.js route handlers, so it
 * MUST stay free of Node-only APIs and must NEVER throw at module-evaluation
 * time (a throw here takes the whole app down on Railway boot).
 *
 * Backend URL resolution priority (first non-empty wins):
 *   1. BACKEND_AUTH_URL          (explicit, full URL to /auth/login)
 *   2. NEXT_PUBLIC_API_URL       (preferred — what we tell operators to set)
 *   3. BACKEND_API_URL           (legacy server-only name, still supported)
 *   4. PRODUCTION_BACKEND_FALLBACK (hard-coded last-resort)
 *
 * Why a hard-coded fallback?
 *   If Railway forgets a variable, login MUST still work. The fallback points
 *   at the canonical K.U.A. FastAPI service. Override it by setting one of
 *   the env vars above in Railway → Variables.
 *
 * Required vars for production hardening (set in Railway):
 *   AUTH_SECRET           — 48+ random bytes used to sign session JWTs.
 *   NEXT_PUBLIC_API_URL   — FastAPI base URL (recommended).
 */

/** Canonical production backend URL — hard fallback. */
const PRODUCTION_BACKEND_FALLBACK =
  "https://kua-urban-agent-production.up.railway.app";

const env = (key: string, fallback = ""): string => {
  const v = process.env[key];
  if (v === undefined || v === null || v === "") return fallback;
  return v;
};

const num = (key: string, fallback: number): number => {
  const raw = process.env[key];
  if (raw === undefined || raw === null || raw === "") return fallback;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : fallback;
};

const trimSlash = (s: string): string => s.replace(/\/+$/, "");

function firstNonEmpty(...candidates: string[]): string {
  for (const c of candidates) {
    if (c && c.trim().length > 0) return c.trim();
  }
  return "";
}

const RESOLVED_API_URL = trimSlash(
  firstNonEmpty(
    env("NEXT_PUBLIC_API_URL"),
    env("BACKEND_API_URL"),
    PRODUCTION_BACKEND_FALLBACK
  )
);

const RESOLVED_AUTH_URL = firstNonEmpty(
  trimSlash(env("BACKEND_AUTH_URL")),
  RESOLVED_API_URL ? `${RESOLVED_API_URL}/auth/login` : ""
);

const SECRET_FALLBACK = "dev-only-insecure-secret-CHANGE-ME-32+bytes-min";
const rawSecret = env("AUTH_SECRET", SECRET_FALLBACK);
if (rawSecret === SECRET_FALLBACK && process.env.NODE_ENV === "production") {
  console.warn(
    "[kua-auth] AUTH_SECRET is not set in production — using insecure fallback. " +
      "Set AUTH_SECRET in Railway → Variables immediately."
  );
}

export const authConfig = {
  /** Cookie name used by route handlers AND middleware. */
  cookieName: env("AUTH_COOKIE_NAME", "kua_session"),

  /** Session TTL in seconds. */
  ttlSeconds: num("AUTH_SESSION_TTL_SECONDS", 43200),

  /** HS256 signing secret. */
  secret: rawSecret,

  /** Effective FastAPI login URL. Always populated in this build. */
  backendAuthUrl: RESOLVED_AUTH_URL,

  /** Effective FastAPI base URL (used by the /api/proxy route). */
  backendApiUrl: RESOLVED_API_URL,

  /** Optional local break-glass operator (dev only). */
  operator: {
    username: env("AUTH_OPERATOR_USERNAME"),
    passwordHash: env("AUTH_OPERATOR_PASSWORD_HASH"),
    displayName: env("AUTH_OPERATOR_DISPLAY_NAME", "Acquisitions Operator"),
    clearance: env("AUTH_OPERATOR_CLEARANCE", "tier-1"),
  },
} as const;

/** Diagnostic — exposed only by /api/auth/debug, never user-facing. */
export const authDebug = {
  resolvedFrom: env("NEXT_PUBLIC_API_URL")
    ? "NEXT_PUBLIC_API_URL"
    : env("BACKEND_API_URL")
    ? "BACKEND_API_URL"
    : env("BACKEND_AUTH_URL")
    ? "BACKEND_AUTH_URL"
    : "PRODUCTION_BACKEND_FALLBACK",
  hasAuthSecret: rawSecret !== SECRET_FALLBACK,
  nodeEnv: process.env.NODE_ENV ?? "unknown",
};

export const SESSION_COOKIE = authConfig.cookieName;
export const isProd = process.env.NODE_ENV === "production";
