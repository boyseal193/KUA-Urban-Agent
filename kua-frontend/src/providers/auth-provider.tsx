"use client";

import * as React from "react";
import type { AuthSessionUser } from "@/lib/api/types";

interface AuthContextValue {
  user: AuthSessionUser | null;
  isLoading: boolean;
  refresh: () => Promise<AuthSessionUser | null>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

interface SessionResponse {
  authenticated: boolean;
  user: AuthSessionUser | null;
}

export function AuthProvider({
  children,
  initialUser,
}: {
  children: React.ReactNode;
  initialUser: AuthSessionUser | null;
}) {
  const [user, setUser] = React.useState<AuthSessionUser | null>(initialUser);
  const [isLoading, setLoading] = React.useState(false);

  const refresh = React.useCallback(async (): Promise<AuthSessionUser | null> => {
    setLoading(true);
    try {
      const res = await fetch("/api/auth/session", {
        cache: "no-store",
        credentials: "include",
      });
      if (!res.ok) {
        setUser(null);
        return null;
      }
      const data = (await res.json()) as SessionResponse;
      const next = data.authenticated ? data.user : null;
      setUser(next);
      return next;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = React.useCallback(async () => {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "include",
        cache: "no-store",
      });
    } catch {
      // ignore — we'll still wipe local state and bounce to /login
    }
    setUser(null);
    // Hard navigation guarantees the cleared cookie is what the next
    // request carries; router.replace can race the Set-Cookie write.
    window.location.assign("/login");
  }, []);

  const value = React.useMemo<AuthContextValue>(
    () => ({ user, isLoading, refresh, logout }),
    [user, isLoading, refresh, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
