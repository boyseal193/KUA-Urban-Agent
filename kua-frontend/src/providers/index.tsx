"use client";

import * as React from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { QueryProvider } from "./query-provider";
import { AuthProvider } from "./auth-provider";
import type { AuthSessionUser } from "@/lib/api/types";

export function AppProviders({
  children,
  initialUser,
}: {
  children: React.ReactNode;
  initialUser: AuthSessionUser | null;
}) {
  return (
    <QueryProvider>
      <AuthProvider initialUser={initialUser}>
        <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
        <Toaster />
      </AuthProvider>
    </QueryProvider>
  );
}
