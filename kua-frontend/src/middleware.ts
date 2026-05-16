import { NextResponse, type NextRequest } from "next/server";
import { verifySession } from "@/lib/auth/jwt";
import { SESSION_COOKIE } from "@/lib/auth/config";

const PUBLIC_PATHS = ["/login", "/api/auth/login", "/api/auth/session"];

function isPublic(pathname: string) {
  if (PUBLIC_PATHS.includes(pathname)) return true;
  if (pathname.startsWith("/_next")) return true;
  if (pathname.startsWith("/favicon")) return true;
  if (pathname.startsWith("/fonts")) return true;
  if (pathname.startsWith("/assets")) return true;
  if (pathname === "/manifest.json" || pathname === "/robots.txt") return true;
  return false;
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (isPublic(pathname)) return NextResponse.next();

  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const payload = token ? await verifySession(token) : null;

  if (!payload) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { error: "UNAUTHORIZED" },
        { status: 401 }
      );
    }
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  // Authenticated users hitting /login bounce to dashboard
  if (pathname === "/login") {
    const url = req.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|favicon.ico|fonts|assets|manifest.json|robots.txt).*)"],
};
