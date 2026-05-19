/**
 * Next.js Edge middleware — single source of truth for protected-route
 * enforcement.
 *
 * Rules:
 *   • Public paths (always allow): /login, /api/auth/*, /api/healthz,
 *     static assets, common metadata files.
 *   • Any other path requires a valid JWT in the SESSION_COOKIE cookie.
 *   • Unauthenticated browser navigation → redirect to /login?next=<orig>.
 *   • Unauthenticated API call → 401 JSON.
 *   • Authenticated user hitting /login → bounce to /dashboard (or ?next=).
 *
 * This runs on the Edge runtime so it MUST NOT import bcrypt, next/headers,
 * or anything from `server-only`.
 */
import { NextResponse, type NextRequest } from "next/server";
import { verifySession } from "@/lib/auth/jwt";
import { SESSION_COOKIE } from "@/lib/auth/config";

const PUBLIC_EXACT = new Set<string>([
  "/login",
  "/api/auth/login",
  "/api/auth/logout",
  "/api/auth/session",
  "/api/healthz",
  "/favicon.ico",
  "/manifest.json",
  "/robots.txt",
  "/sitemap.xml",
]);

const PUBLIC_PREFIXES = [
  "/_next/",
  "/fonts/",
  "/assets/",
  "/images/",
  "/icons/",
  "/static/",
];

function isPublic(pathname: string): boolean {
  if (PUBLIC_EXACT.has(pathname)) return true;
  for (const p of PUBLIC_PREFIXES) {
    if (pathname.startsWith(p)) return true;
  }
  return false;
}

function isApiPath(pathname: string): boolean {
  return pathname.startsWith("/api/");
}

function isSafeNext(value: string | null): value is string {
  if (!value) return false;
  // must be a same-origin absolute path, not a protocol-relative URL
  return value.startsWith("/") && !value.startsWith("//");
}

export async function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;

  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const payload = token ? await verifySession(token) : null;
  const authed = Boolean(payload);

  // Already on /login? Redirect away if already authed; otherwise let it render.
  if (pathname === "/login") {
    if (authed) {
      const url = req.nextUrl.clone();
      const next = req.nextUrl.searchParams.get("next");
      url.pathname = isSafeNext(next) ? next : "/dashboard";
      url.search = "";
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  // Everything else under the public allowlist passes through.
  if (isPublic(pathname)) {
    return NextResponse.next();
  }

  // Protected path — require a valid session.
  if (!authed) {
    if (isApiPath(pathname)) {
      return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
    }
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

/**
 * Skip the middleware for Next.js internals and well-known static files.
 * Everything else flows through the handler above.
 */
export const config = {
  matcher: [
    "/((?!_next/static|_next/image|_next/data|favicon.ico|robots.txt|sitemap.xml|manifest.json).*)",
  ],
};
