/**
 * Next.js Edge middleware — single source of truth for protected-route
 * enforcement.
 *
 * Rules:
 *   • Public paths (always allow): /login, /api/auth/*, /api/healthz,
 *     static assets, common metadata files.
 *   • Any other path requires a valid JWT in the SESSION_COOKIE cookie
 *     (default name: kua_session).
 *   • Unauthenticated browser navigation → redirect to /login?next=<orig>.
 *   • Unauthenticated API call → 401 JSON.
 *   • Authenticated user hitting /login → bounce to /dashboard (or ?next=).
 *
 * Runs on the Edge runtime — MUST NOT import bcrypt, next/headers, or
 * anything from `server-only`.
 */
import { NextResponse, type NextRequest } from "next/server";
import { verifySession } from "@/lib/auth/jwt";
import { SESSION_COOKIE } from "@/lib/auth/config";

const PUBLIC_EXACT = new Set<string>([
  "/login",
  "/api/auth/login",
  "/api/auth/logout",
  "/api/auth/session",
  "/api/auth/debug",
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
  return value.startsWith("/") && !value.startsWith("//");
}

export async function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;

  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const payload = token ? await verifySession(token) : null;
  const authed = Boolean(payload);

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

  if (isPublic(pathname)) {
    return NextResponse.next();
  }

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

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|_next/data|favicon.ico|robots.txt|sitemap.xml|manifest.json).*)",
  ],
};
