import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="relative z-10 flex min-h-screen items-center justify-center px-4">
      <div className="panel-strong max-w-md p-10 text-center">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          E404 · UNRECOGNISED COORDINATE
        </p>
        <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight">
          Channel offline
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The asset or surface you tried to reach is not available on this
          deployment.
        </p>
        <div className="mt-6 flex items-center justify-center gap-2">
          <Link href="/dashboard">
            <Button variant="tactical">Return to Command</Button>
          </Link>
        </div>
      </div>
    </main>
  );
}
