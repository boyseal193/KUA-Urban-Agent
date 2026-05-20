"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Loader2,
  RadioTower,
  RefreshCcw,
  Sparkles,
  X,
} from "lucide-react";
import * as React from "react";

import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ScanPhase } from "@/hooks/use-scan";
import type {
  ScanErrorRecord,
  ScanJobRecord,
  ScanLogRecord,
  ScanStepRecord,
} from "@/lib/api/types";
import { ExportButtons } from "./export-buttons";

interface ScanProgressProps {
  phase: ScanPhase;
  progress: number;
  job?: ScanJobRecord | null;
  steps?: ScanStepRecord[];
  logs?: ScanLogRecord[];
  errors?: ScanErrorRecord[];
  scannedCount?: number;
  approvedCount?: number;
  error?: string | null;
  onCancel?: () => void;
  onRetry?: () => void;
  onReset?: () => void;
  isPolling?: boolean;
}

const MACRO_STEPS: { phase: ScanPhase; label: string; sub: string }[] = [
  { phase: "queued", label: "Queue dispatch", sub: "Job registered — worker will claim it" },
  { phase: "scraping", label: "Listing acquisition", sub: "Collecting URLs and scraping Idealista" },
  { phase: "analysing", label: "AI extraction", sub: "Structured underwriting input from raw listings" },
  { phase: "scoring", label: "Scoring & memo", sub: "Auto-scoring + IC memo generation" },
  { phase: "exporting", label: "Export artifacts", sub: "Excel workbook and persistence" },
];

const ORDER: ScanPhase[] = [
  "idle",
  "queued",
  "running",
  "scraping",
  "analysing",
  "scoring",
  "exporting",
  "complete",
  "error",
  "cancelled",
];

function indexOf(p: ScanPhase) {
  return ORDER.indexOf(p);
}

export function ScanProgress({
  phase,
  progress,
  job,
  steps,
  logs,
  errors,
  scannedCount,
  approvedCount,
  error,
  onCancel,
  onRetry,
  onReset,
  isPolling,
}: ScanProgressProps) {
  const [showLogs, setShowLogs] = React.useState(false);
  const safeSteps = steps ?? [];
  const safeLogs = logs ?? [];
  const safeErrors = errors ?? [];
  const currentIdx = indexOf(phase);
  const safeProgress = Number.isFinite(progress)
    ? Math.max(0, Math.min(100, progress))
    : 0;

  const runningStep = safeSteps.find((s) => s.status === "running");
  const failedSteps = safeSteps.filter((s) => s.status === "failed");
  const isTerminalError = phase === "error" || phase === "cancelled";

  return (
    <div className="panel relative overflow-hidden p-5">
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <RadioTower className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">Scan Pipeline</h3>
        </div>
        <div className="flex items-center gap-2">
          {job?.id && (
            <span className="hidden font-mono text-[9px] text-muted-foreground sm:inline">
              {job.id.slice(0, 8)}…
            </span>
          )}
          {isPolling && onCancel && (
            <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          )}
          {isTerminalError && onRetry && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onRetry}
              className="gap-1"
            >
              <RefreshCcw className="h-3 w-3" />
              Retry
            </Button>
          )}
          {isTerminalError && onReset && (
            <Button type="button" size="sm" variant="ghost" onClick={onReset}>
              Dismiss
            </Button>
          )}
          <span
            className={cn(
              "font-mono text-[10px] uppercase tracking-widest",
              phase === "complete"
                ? "text-accent"
                : phase === "error"
                ? "text-destructive"
                : phase === "cancelled"
                ? "text-kua-amber"
                : "text-primary"
            )}
          >
            {phaseLabel(phase)}
          </span>
        </div>
      </div>

      <Progress value={safeProgress} className="mb-2 h-1" />

      <div className="mb-4 flex flex-wrap gap-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        <span>
          {job?.listings_done ?? scannedCount ?? 0}/{job?.listings_total ?? "—"} listings
        </span>
        <span>{approvedCount ?? job?.approved_count ?? 0} approved</span>
        {runningStep && (
          <span className="text-primary">step · {runningStep.step_key}</span>
        )}
        {failedSteps.length > 0 && (
          <span className="text-destructive">
            {failedSteps.length} step failures
          </span>
        )}
      </div>

      <div className="space-y-2">
        {MACRO_STEPS.map((s, i) => {
          const sIdx = indexOf(s.phase);
          const done =
            currentIdx > sIdx && phase !== "error" && phase !== "cancelled";
          const active =
            currentIdx === sIdx ||
            (phase === "running" && s.phase === "scraping");
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
                    {String(i + 1).padStart(2, "0")}
                  </span>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-foreground">
                  {s.label}
                </div>
                <div className="text-[10px] text-muted-foreground">{s.sub}</div>
              </div>
            </motion.div>
          );
        })}
      </div>

      <AnimatePresence>
        {phase === "complete" && (
          <motion.div
            key="complete-banner"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-4 flex items-center gap-2 rounded-md border border-accent/30 bg-accent/[0.06] px-3 py-2 text-xs text-accent"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Scan complete — {scannedCount ?? job?.listings_done ?? "—"}{" "}
            properties ingested, {approvedCount ?? job?.approved_count ?? "—"}{" "}
            approved for due diligence.
          </motion.div>
        )}
        {phase === "complete" && job?.id && (
          <motion.div
            key="complete-exports"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="mt-4 rounded-md border border-border/60 bg-card/40 p-3"
          >
            <ExportButtons jobId={job.id} />
          </motion.div>
        )}
        {isTerminalError && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-4 flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/[0.06] px-3 py-2 text-xs text-destructive"
          >
            <X className="h-3.5 w-3.5" />
            {error || job?.error_message || "Scan failed. Inspect logs and retry."}
          </motion.div>
        )}
      </AnimatePresence>

      {(safeLogs.length > 0 || safeErrors.length > 0) && (
        <div className="mt-4 border-t border-border/60 pt-3">
          <button
            type="button"
            onClick={() => setShowLogs((v) => !v)}
            className="flex w-full items-center justify-between text-left text-xs font-medium text-foreground"
          >
            Pipeline logs ({safeLogs.length}) · errors ({safeErrors.length})
            {showLogs ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>
          {showLogs && (
            <div className="mt-2 max-h-48 space-y-1 overflow-y-auto rounded-md border border-border/40 bg-black/20 p-2 font-mono text-[10px]">
              {safeErrors.map((e) => (
                <div key={e.id} className="text-destructive">
                  [{formatTs(e.created_at)}] {e.error_type}:{" "}
                  {(e.message ?? "").slice(0, 240)}
                </div>
              ))}
              {safeLogs.map((l) => (
                <div key={l.id} className="text-muted-foreground">
                  [{formatTs(l.created_at)}] {l.level}:{" "}
                  {(l.message ?? "").slice(0, 240)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatTs(s: string | undefined | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleTimeString();
  } catch {
    return s;
  }
}

function phaseLabel(p: ScanPhase) {
  switch (p) {
    case "idle":
      return "STANDBY";
    case "queued":
      return "QUEUED";
    case "running":
      return "RUNNING";
    case "scraping":
      return "ACQUIRING";
    case "analysing":
      return "EXTRACTING";
    case "scoring":
      return "SCORING";
    case "exporting":
      return "EXPORTING";
    case "complete":
      return "COMPLETE";
    case "error":
      return "FAULT";
    case "cancelled":
      return "CANCELLED";
    default:
      return "STANDBY";
  }
}
