"use client";

import * as React from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, MapPin, Sparkles } from "lucide-react";

import { ScoreBadge } from "@/components/dashboard/score-badge";
import { DealStatusIndicator } from "@/components/dashboard/deal-status-indicator";
import { Badge } from "@/components/ui/badge";
import { moneyCompact, metersLabel } from "@/lib/format";
import { verdictMeta } from "@/lib/constants";
import { useStaleProperties } from "@/lib/stale-properties";
import { cn } from "@/lib/utils";

import type { AnalysisResult } from "@/lib/api/types";

interface LiveScanFeedProps {
  results?: AnalysisResult[] | null;
  className?: string;
  emptyHint?: string;
  title?: string;
}

export function LiveScanFeed({
  results,
  className,
  emptyHint = "Awaiting scan output. Launch an acquisition sweep above.",
  title = "Live Acquisition Feed",
}: LiveScanFeedProps) {
  const { isStale } = useStaleProperties();

  const list = React.useMemo(() => {
    if (!Array.isArray(results)) return [];
    return results
      .filter((r): r is AnalysisResult => Boolean(r && r.property_id))
      .filter((r) => !isStale(r.property_id))
      .slice(0, 20);
  }, [results, isStale]);

  return (
    <div className={cn("panel relative overflow-hidden p-5", className)}>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {list.length} listings
        </span>
      </div>

      {list.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border/60 bg-white/[0.01] px-4 py-10 text-center">
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Standby
          </span>
          <p className="max-w-xs text-xs text-muted-foreground">{emptyHint}</p>
        </div>
      ) : (
        <ul className="relative space-y-2">
          <span className="pointer-events-none absolute inset-y-0 left-[15px] w-px bg-gradient-to-b from-primary/40 via-primary/10 to-transparent" />
          <AnimatePresence initial>
            {list.map((r, idx) => {
              const ex = r.extracted ?? {};
              const verdict = verdictMeta(r.score?.verdict);
              return (
                <motion.li
                  key={r.property_id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.03 }}
                  className="group relative ml-7 rounded-md border border-border/40 bg-white/[0.015] p-3 transition-colors hover:border-primary/40 hover:bg-primary/[0.03]"
                >
                  <span
                    className="absolute -left-[27px] top-3 inline-flex h-3 w-3 items-center justify-center rounded-full border border-primary/40 bg-card"
                    aria-hidden
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-primary shadow-glow" />
                  </span>

                  <div className="flex items-start gap-3">
                    <ScoreBadge score={r.score?.score} size="sm" showTier={false} />
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <DealStatusIndicator status={r.deal_status} />
                        <Badge className={verdict.chipClass}>{verdict.label}</Badge>
                        <span className="ml-auto font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                          {new Date().toLocaleTimeString("en-EU", {
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </span>
                      </div>
                      <Link
                        href={`/deals/${r.property_id}`}
                        className="block truncate text-sm font-medium text-foreground hover:text-primary"
                      >
                        {ex.address || ex.neighbourhood || "Untitled listing"}
                      </Link>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <MapPin className="h-3 w-3" />
                          {ex.neighbourhood ?? "—"}
                        </span>
                        <span className="font-mono tabular-nums">
                          {moneyCompact(ex.asking_price ?? null)} ·{" "}
                          {metersLabel(ex.gba_m2 ?? null)}
                        </span>
                      </div>
                    </div>
                    <Link
                      href={`/deals/${r.property_id}`}
                      className="opacity-0 transition group-hover:opacity-100"
                    >
                      <ArrowUpRight className="h-3.5 w-3.5 text-primary" />
                    </Link>
                  </div>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      )}
    </div>
  );
}
