"use client";

/**
 * Floating "active scan" indicator.
 *
 * Visible on every dashboard page when a scan is running OR was running but
 * the operator navigated away before it completed. Tapping it returns to
 * /scan and the live progress view picks up exactly where it left off
 * (the polling loop never stopped — see ActiveScanProvider).
 */

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Radar, X, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";

import { useActiveScan } from "@/lib/contexts/active-scan-context";
import { cn } from "@/lib/utils";

const STATE_META: Record<
  string,
  { label: string; tone: string; icon: React.ComponentType<{ className?: string }> }
> = {
  queued:    { label: "Queued",   tone: "border-amber-500/40 bg-amber-500/[0.08] text-amber-200",      icon: Loader2 },
  running:   { label: "Running",  tone: "border-primary/40 bg-primary/[0.08] text-primary",            icon: Loader2 },
  scraping:  { label: "Scraping", tone: "border-primary/40 bg-primary/[0.08] text-primary",            icon: Loader2 },
  analysing: { label: "Analysing",tone: "border-primary/40 bg-primary/[0.08] text-primary",            icon: Loader2 },
  scoring:   { label: "Scoring",  tone: "border-primary/40 bg-primary/[0.08] text-primary",            icon: Loader2 },
  exporting: { label: "Exporting",tone: "border-cyan-500/40 bg-cyan-500/[0.08] text-cyan-200",         icon: Loader2 },
  complete:  { label: "Complete", tone: "border-emerald-500/40 bg-emerald-500/[0.08] text-emerald-200",icon: CheckCircle2 },
  error:     { label: "Failed",   tone: "border-destructive/40 bg-destructive/[0.08] text-destructive",icon: AlertTriangle },
  cancelled: { label: "Cancelled",tone: "border-muted/40 bg-muted/[0.08] text-muted-foreground",       icon: X },
};

export function ActiveScanBanner() {
  const scan = useActiveScan();
  const pathname = usePathname();

  // Hide on /scan — the full progress UI is already visible there.
  const onScanPage = pathname?.startsWith("/scan") ?? false;
  const hasActive = Boolean(scan.jobId) && scan.phase !== "idle";

  // We deliberately keep the banner visible for ~10s after completion so
  // operators away from /scan see the success / error and can click in.
  const [dismissed, setDismissed] = React.useState(false);
  React.useEffect(() => {
    // Reset dismissed state when a new scan starts.
    if (scan.isPolling) setDismissed(false);
  }, [scan.isPolling, scan.jobId]);

  if (!hasActive || onScanPage || dismissed) return null;

  const meta = STATE_META[scan.phase] ?? STATE_META.running;
  const Icon = meta.icon;
  const isLive = scan.isPolling;
  const counters = {
    done: scan.job?.listings_done ?? 0,
    total: scan.job?.listings_total ?? 0,
  };

  return (
    <AnimatePresence>
      <motion.div
        key="active-scan-banner"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 12 }}
        transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
        className="pointer-events-none fixed bottom-4 right-4 z-50 sm:bottom-6 sm:right-6"
      >
        <div
          className={cn(
            "pointer-events-auto flex max-w-sm items-stretch gap-0 overflow-hidden rounded-lg border bg-card/90 shadow-glow backdrop-blur-xl",
            meta.tone
          )}
        >
          <Link
            href="/scan"
            className="group flex flex-1 items-center gap-3 px-4 py-3 transition hover:bg-white/[0.04]"
            aria-label="View live scan"
          >
            <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-current/20 bg-current/10">
              {isLive ? (
                <Icon className="h-4 w-4 animate-spin" />
              ) : (
                <Icon className="h-4 w-4" />
              )}
              {isLive && (
                <span className="absolute -right-0.5 -top-0.5 inline-flex h-2 w-2 rounded-full bg-current">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
                </span>
              )}
            </div>
            <div className="min-w-0 leading-tight">
              <div className="flex items-center gap-2">
                <Radar className="h-3 w-3 opacity-70" />
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] opacity-80">
                  {meta.label}
                </span>
              </div>
              <div className="mt-0.5 truncate text-xs font-semibold">
                {scan.job?.current_step
                  ? humanStep(scan.job.current_step)
                  : "Scan in progress"}
              </div>
              <div className="mt-0.5 truncate font-mono text-[10px] opacity-70">
                {counters.total > 0
                  ? `${counters.done} / ${counters.total} listings · ${scan.progress}%`
                  : `${scan.progress}%`}
              </div>
            </div>
          </Link>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              setDismissed(true);
            }}
            className="flex shrink-0 items-center justify-center border-l border-current/20 px-2 text-current/70 transition hover:bg-white/[0.04] hover:text-current"
            aria-label="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

function humanStep(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
