/**
 * Runtime auth configuration.
 *
 * Values come from environment variables — never hard-code credentials.
 * In production, configure these in the Vercel / Railway / Docker dashboard.
 */

const required = (key: string, fallback?: string) => {
  const v = process.env[key] ?? fallback;
  if (!v && process.env.NODE_ENV === "production") {
    throw new Error(`Missing required env var: ${key}`);
  }
  return v ?? "";
};

export const authConfig = {
  cookieName: process.env.AUTH_COOKIE_NAME || "kua_session",
  ttlSeconds: Number(process.env.AUTH_SESSION_TTL_SECONDS || 43200), // 12h
  secret: required("AUTH_SECRET", "dev-only-insecure-secret-change-me"),
  operator: {
    username: process.env.AUTH_OPERATOR_USERNAME || "operator",
    passwordHash: process.env.AUTH_OPERATOR_PASSWORD_HASH || "",
    displayName:
      process.env.AUTH_OPERATOR_DISPLAY_NAME || "Acquisitions Operator",
    clearance: process.env.AUTH_OPERATOR_CLEARANCE || "tier-1",
  },
  /** Optional FastAPI auth proxy. If set, /api/auth/login proxies through here. */
  backendAuthUrl: process.env.BACKEND_AUTH_URL || "",
};

export const SESSION_COOKIE = authConfig.cookieName;
