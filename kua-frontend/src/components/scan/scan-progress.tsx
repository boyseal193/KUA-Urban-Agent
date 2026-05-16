"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Check, Loader2, RadioTower, Sparkles, X } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { ScanPhase } from "@/hooks/use-scan";

interface ScanProgressProps {
  phase: ScanPhase;
  progress: number;
  scannedCount?: number;
  approvedCount?: number;
  error?: string | null;
}

const STEPS: { phase: ScanPhase; label: string; sub: string }[] = [
  { phase: "queued", label: "Queue dispatch", sub: "Operator request relayed to scan engine" },
  { phase: "scraping", label: "Listing acquisition", sub: "Crawling Idealista corridor results" },
  { phase: "analysing", label: "AI extraction", sub: "Structured underwriting input from raw listings" },
  { phase: "scoring", label: "Scoring & memo", sub: "Auto-scoring + IC memo generation" },
];

const ORDER: ScanPhase[] = [
  "idle",
  "queued",
  "scraping",
  "analysing",
  "scoring",
  "complete",
  "error",
];

function indexOf(p: ScanPhase) {
  return ORDER.indexOf(p);
}

export function ScanProgress({
  phase,
  progress,
  scannedCount,
  approvedCount,
  error,
}: ScanProgressProps) {
  const currentIdx = indexOf(phase);
  return (
    <div className="panel relative overflow-hidden p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RadioTower className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            Scan Pipeline
          </h3>
        </div>
        <span
          className={cn(
            "font-mono text-[10px] uppercase tracking-widest",
            phase === "complete"
              ? "text-accent"
              : phase === "error"
              ? "text-destructive"
              : "text-primary"
          )}
        >
          {phaseLabel(phase)}
        </span>
      </div>

      <Progress value={progress} className="mb-4 h-1" />

      <div className="space-y-2">
        {STEPS.map((s) => {
          const sIdx = indexOf(s.phase);
          const done = currentIdx > sIdx && phase !== "error";
          const active = currentIdx === sIdx;
          return (
            <motion.div
              key={s.phase}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              className={cn(
                "flex items-center gap-3 rounded-md border px-3 py-2 transition-colors",
                done
                  ? "border-accent/30 bg-accent/[0.04]"
                  : active
                  ? "border-primary/40 bg-primary/[0.06] shadow-glow"
                  : "border-border/40 bg-white/[0.01]"
              )}
            >
              <div
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-md border",
                  done
                    ? "border-accent/40 bg-accent/15 text-accent"
                    : active
                    ? "border-primary/40 bg-primary/15 text-primary"
                    : "border-border/60 bg-white/[0.03] text-muted-foreground"
                )}
              >
                {done ? (
                  <Check className="h-3 w-3" />
                ) : active ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <span className="text-[10px] font-mono">
                    {String(STEPS.indexOf(s) + 1).padStart(2, "0")}
                  </span>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-foreground">
                  {s.label}
                </div>
                <div className="text-[10px] text-muted-foreground">{s.sub}</div>
              </div>
              {active && (
                <span className="font-mono text-[10px] uppercase tracking-widest text-primary">
                  EXEC
                </span>
              )}
            </motion.div>
          );
        })}
      </div>

      <AnimatePresence>
        {phase === "complete" && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-4 flex items-center gap-2 rounded-md border border-accent/30 bg-accent/[0.06] px-3 py-2 text-xs text-accent"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Scan complete — {scannedCount ?? "—"} properties ingested,{" "}
            {approvedCount ?? "—"} approved for due diligence.
          </motion.div>
        )}
        {phase === "error" && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-4 flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/[0.06] px-3 py-2 text-xs text-destructive"
          >
            <X className="h-3.5 w-3.5" />
            {error || "Scan failed. Inspect logs and retry."}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function phaseLabel(p: ScanPhase) {
  switch (p) {
    case "idle":
      return "STANDBY";
    case "queued":
      return "QUEUED";
    case "scraping":
      return "ACQUIRING";
    case "analysing":
      return "EXTRACTING";
    case "scoring":
      return "SCORING";
    case "complete":
      return "COMPLETE";
    case "error":
      return "FAULT";
  }
}
