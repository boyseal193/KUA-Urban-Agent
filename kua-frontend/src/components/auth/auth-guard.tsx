"use client";

import * as React from "react";
import { useAuth } from "@/providers/auth-provider";

/**
 * Passive render guard.
 *
 * The authoritative redirect lives in `middleware.ts` and the dashboard
 * layout already runs a server-side `getSession()` check. This component
 * therefore does NOT issue any client-side router redirects — doing so was
 * the source of the production "redirects back to login" race condition.
 *
 * It simply hides protected content if the React-side `user` is null
 * (e.g. after a `logout()` call inside the same client navigation).
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return null;
  return <>{children}</>;
}
