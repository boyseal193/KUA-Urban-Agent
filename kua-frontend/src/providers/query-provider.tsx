"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error: any) => {
          if (error?.status === 401 || error?.status === 403) return false;
          return failureCount < 2;
        },
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

let browserClient: QueryClient | undefined;
function getQueryClient() {
  if (typeof window === "undefined") return makeClient();
  if (!browserClient) browserClient = makeClient();
  return browserClient;
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const client = getQueryClient();
  return (
    <QueryClientProvider client={client}>
      {children}
      {process.env.NODE_ENV !== "production" && (
        <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-left" />
      )}
    </QueryClientProvider>
  );
}
