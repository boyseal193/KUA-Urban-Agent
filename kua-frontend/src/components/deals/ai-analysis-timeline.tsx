"use client";

import { motion } from "framer-motion";
import {
  Brain,
  CheckCircle2,
  Cpu,
  FileText,
  Gauge,
  MapPin,
  Scan,
} from "lucide-react";
import type { AnalysisRecord, PropertyRecord } from "@/lib/api/types";

interface AiAnalysisTimelineProps {
  property: PropertyRecord;
  analysis?: AnalysisRecord | null;
  className?: string;
}

export function AiAnalysisTimeline({
  property,
  analysis,
  className,
}: AiAnalysisTimelineProps) {
  const events = [
    {
      icon: Scan,
      label: "Listing acquired",
      detail: "Source crawled and raw text captured",
      complete: true,
    },
    {
      icon: Cpu,
      label: "GPT-5 extraction",
      detail: "Structured underwriting input produced",
      complete: !!analysis?.input,
    },
    {
      icon: MapPin,
      label: "Geo-resolution",
      detail:
        property.latitude && property.longitude
          ? `Coordinates ${property.latitude.toFixed(4)}, ${property.longitude.toFixed(4)}`
          : "Awaiting coordinates",
      complete: !!property.latitude,
    },
    {
      icon: Gauge,
      label: "Economics underwritten",
      detail: "Revenue / capex / yield calculated",
      complete: !!analysis?.economics,
    },
    {
      icon: Brain,
      label: "AI scoring",
      detail: `Composite score ${analysis?.score?.score ?? property.score ?? "—"}/100`,
      complete: !!analysis?.score,
    },
    {
      icon: FileText,
      label: "IC memo drafted",
      detail: "Markdown memo persisted",
      complete: !!analysis?.ic_memo,
    },
  ];

  return (
    <div className={`panel p-5 ${className ?? ""}`}>
      <header className="mb-3 flex items-center justify-between border-b border-border/60 pb-3">
        <h3 className="text-sm font-semibold text-foreground">
          AI Analysis Timeline
        </h3>
        <span className="font-mono text-[10px] uppercase tracking-widest text-accent">
          PIPELINE COMPLETE
        </span>
      </header>

      <ol className="relative space-y-3 pl-6">
        <span
          aria-hidden
          className="pointer-events-none absolute left-[10px] top-1 h-[calc(100%-8px)] w-px bg-gradient-to-b from-primary/50 via-primary/20 to-transparent"
        />
        {events.map((e, i) => {
          const Icon = e.icon;
          return (
            <motion.li
              key={e.label}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              className="relative"
            >
              <span className="absolute -left-[22px] top-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full border border-primary/40 bg-card">
                <CheckCircle2
                  className={`h-2.5 w-2.5 ${
                    e.complete ? "text-primary" : "text-muted-foreground"
                  }`}
                />
              </span>
              <div className="flex items-start gap-2">
                <Icon className="mt-0.5 h-3.5 w-3.5 text-muted-foreground" />
                <div>
                  <div className="text-xs font-semibold text-foreground">
                    {e.label}
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    {e.detail}
                  </div>
                </div>
              </div>
            </motion.li>
          );
        })}
      </ol>
    </div>
  );
}
