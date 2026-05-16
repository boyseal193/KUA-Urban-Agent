"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/providers/auth-provider";

/**
 * Client-side belt-and-suspenders guard.
 * The real enforcement happens in middleware.ts, but this prevents flashes
 * of protected content during client-side navigation when a token expires.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (!user) router.replace("/login");
  }, [user, router]);

  if (!user) return null;
  return <>{children}</>;
}
