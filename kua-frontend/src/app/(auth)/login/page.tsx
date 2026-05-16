import type { Metadata } from "next";
import { Suspense } from "react";
import { Activity, Lock, Radio } from "lucide-react";
import { LoginForm } from "@/components/auth/login-form";
import { APP_NAME, APP_SHORT, APP_VERSION } from "@/lib/constants";

export const metadata: Metadata = {
  title: "Secure Access",
  description: "K.U.A. operator authentication portal.",
};

export default function LoginPage() {
  return (
    <div className="w-full max-w-md">
      <LoginShell>
        <Suspense>
          <LoginForm />
        </Suspense>
      </LoginShell>
    </div>
  );
}

function LoginShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative">
      <Corner position="tl" />
      <Corner position="tr" />
      <Corner position="bl" />
      <Corner position="br" />

      <div className="panel-strong relative overflow-hidden p-8 sm:p-10">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative h-9 w-9 overflow-hidden rounded-md border border-primary/40 bg-primary/10">
              <div className="absolute inset-0 flex items-center justify-center font-display text-base font-bold text-primary">
                K
              </div>
              <div className="absolute inset-0 animate-pulse-glow bg-primary/10" />
            </div>
            <div>
              <div className="font-display text-sm font-semibold tracking-wider text-foreground">
                {APP_SHORT}
              </div>
              <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
                {APP_NAME}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/[0.06] px-2 py-1">
            <span className="relative inline-flex h-1.5 w-1.5">
              <span className="absolute inset-0 animate-ping rounded-full bg-accent/70" />
              <span className="relative h-1.5 w-1.5 rounded-full bg-accent shadow-glow-neon" />
            </span>
            <span className="font-mono text-[9px] uppercase tracking-widest text-accent">
              system online
            </span>
          </div>
        </div>

        <div className="mb-7 space-y-2">
          <h1 className="font-display text-2xl font-semibold tracking-tight text-foreground">
            Secure Operator Access
          </h1>
          <p className="text-xs text-muted-foreground">
            Authenticate to enter the K.U.A. acquisitions command surface.
            All activity is logged.
          </p>
        </div>

        {children}

        <div className="mt-8 grid grid-cols-3 gap-3 border-t border-border/50 pt-5 text-[10px] font-mono uppercase tracking-widest text-muted-foreground/70">
          <div className="flex items-center gap-1.5">
            <Lock className="h-3 w-3 text-primary" /> AES-256
          </div>
          <div className="flex items-center gap-1.5">
            <Radio className="h-3 w-3 text-accent" /> Channel SEC
          </div>
          <div className="flex items-center gap-1.5">
            <Activity className="h-3 w-3 text-kua-amber" /> Build {APP_VERSION}
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground/70">
        <span>SECTOR · BARCELONA</span>
        <span>UNAUTHORIZED ACCESS IS PROHIBITED</span>
      </div>
    </div>
  );
}

function Corner({ position }: { position: "tl" | "tr" | "bl" | "br" }) {
  const map = {
    tl: "top-0 left-0 border-t border-l",
    tr: "top-0 right-0 border-t border-r",
    bl: "bottom-0 left-0 border-b border-l",
    br: "bottom-0 right-0 border-b border-r",
  } as const;
  return (
    <span
      aria-hidden
      className={`pointer-events-none absolute h-5 w-5 border-primary/60 ${map[position]}`}
    />
  );
}
