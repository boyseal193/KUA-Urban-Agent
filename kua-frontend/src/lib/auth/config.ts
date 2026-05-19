/**
 * Runtime auth configuration.
 *
 * All values are pulled from environment variables. This module is imported
 * by both Node.js route handlers and the Edge-runtime middleware, so it MUST
 * stay free of Node-only APIs and must NEVER throw at module-evaluation time
 * (a throw here will take the whole app down on Railway / Vercel boot).
 *
 * Required in production (set in Railway → Variables):
 *   AUTH_SECRET           — 48+ random bytes (HS256 signing key).
 *   BACKEND_API_URL       — FastAPI base URL, e.g.
 *                            https://kua-urban-agent-production.up.railway.app
 *
 * Optional:
 *   AUTH_COOKIE_NAME           — default "kua_session"
 *   AUTH_SESSION_TTL_SECONDS   — default 43200 (12h)
 *   BACKEND_AUTH_URL           — full URL to FastAPI login endpoint.
 *                                Defaults to `${BACKEND_API_URL}/auth/login`.
 *   AUTH_OPERATOR_USERNAME     — local fallback operator (dev only)
 *   AUTH_OPERATOR_PASSWORD_HASH — bcrypt hash for the local operator
 *   AUTH_OPERATOR_DISPLAY_NAME — default "Acquisitions Operator"
 *   AUTH_OPERATOR_CLEARANCE    — default "tier-1"
 */

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

const trimSlash = (s: string) => s.replace(/\/+$/, "");

const BACKEND_API_URL = trimSlash(env("BACKEND_API_URL"));

const DERIVED_LOGIN_URL = BACKEND_API_URL ? `${BACKEND_API_URL}/auth/login` : "";

const SECRET_FALLBACK = "dev-only-insecure-secret-CHANGE-ME-32+bytes-min";

/**
 * In production we WARN on a missing AUTH_SECRET but do not throw — throwing
 * here would crash Edge middleware on every request before anything could be
 * logged. The signed JWT will simply use the fallback, which is still a
 * fixed secret per deployment (cryptographically safe enough to boot, but
 * operators MUST set a real secret).
 */
const rawSecret = env("AUTH_SECRET", SECRET_FALLBACK);
if (rawSecret === SECRET_FALLBACK && process.env.NODE_ENV === "production") {
  console.warn(
    "[kua-auth] AUTH_SECRET is not set in production — using insecure fallback. " +
      "Set AUTH_SECRET in Railway → Variables immediately."
  );
}

export const authConfig = {
  cookieName: env("AUTH_COOKIE_NAME", "kua_session"),
  ttlSeconds: num("AUTH_SESSION_TTL_SECONDS", 43200),
  secret: rawSecret,

  /** FastAPI login endpoint. Auto-derived from BACKEND_API_URL if not set. */
  backendAuthUrl: trimSlash(env("BACKEND_AUTH_URL", DERIVED_LOGIN_URL)),

  /** Base FastAPI URL for the proxy route. */
  backendApiUrl: BACKEND_API_URL,

  /** Optional local operator (dev / break-glass account). */
  operator: {
    username: env("AUTH_OPERATOR_USERNAME"),
    passwordHash: env("AUTH_OPERATOR_PASSWORD_HASH"),
    displayName: env("AUTH_OPERATOR_DISPLAY_NAME", "Acquisitions Operator"),
    clearance: env("AUTH_OPERATOR_CLEARANCE", "tier-1"),
  },
} as const;

export const SESSION_COOKIE = authConfig.cookieName;

export const isProd = process.env.NODE_ENV === "production";
