"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import type { AuthSessionUser } from "@/lib/api/types";

interface AuthContextValue {
  user: AuthSessionUser | null;
  isLoading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  initialUser,
}: {
  children: React.ReactNode;
  initialUser: AuthSessionUser | null;
}) {
  const [user, setUser] = React.useState<AuthSessionUser | null>(initialUser);
  const [isLoading, setLoading] = React.useState(false);
  const router = useRouter();

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/auth/session", { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        setUser(data.user ?? null);
      } else {
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = React.useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    setUser(null);
    router.replace("/login");
    router.refresh();
  }, [router]);

  const value = React.useMemo(
    () => ({ user, isLoading, refresh, logout }),
    [user, isLoading, refresh, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
