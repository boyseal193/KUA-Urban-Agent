"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { AlertOctagon } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="relative z-10 flex min-h-screen items-center justify-center px-4">
      <div className="panel-strong max-w-md p-10 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-destructive/40 bg-destructive/10">
          <AlertOctagon className="h-5 w-5 text-destructive" />
        </div>
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-destructive">
          SYSTEM FAULT · {error.digest ?? "trace"}
        </p>
        <h1 className="mt-2 font-display text-2xl font-semibold tracking-tight">
          Pipeline interruption
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{error.message}</p>
        <div className="mt-6 flex items-center justify-center gap-2">
          <Button variant="tactical" onClick={reset}>
            Retry
          </Button>
          <Link href="/dashboard">
            <Button variant="ghost">Return to Command</Button>
          </Link>
        </div>
      </div>
    </main>
  );
}
