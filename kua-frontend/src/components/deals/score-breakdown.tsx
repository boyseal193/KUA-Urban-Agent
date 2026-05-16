"use client";

import { motion } from "framer-motion";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { Brain } from "lucide-react";
import type { AutoScoreBreakdown, DealScore } from "@/lib/api/types";

interface ScoreBreakdownProps {
  score?: DealScore | null;
  className?: string;
}

const FIELDS: { key: keyof AutoScoreBreakdown; label: string; max: number }[] = [
  { key: "location_score", label: "Location", max: 20 },
  { key: "building_score", label: "Building", max: 25 },
  { key: "economics_score", label: "Economics", max: 30 },
  { key: "risk_score", label: "Risk", max: 15 },
  { key: "strategic_fit_score", label: "Strategic Fit", max: 10 },
];

export function ScoreBreakdown({ score, className }: ScoreBreakdownProps) {
  const breakdown = score?.auto_scores;
  const data = FIELDS.map((f) => ({
    metric: f.label,
    value: breakdown ? Number(breakdown[f.key]) || 0 : 0,
    full: f.max,
    pct: breakdown
      ? Math.min(1, (Number(breakdown[f.key]) || 0) / f.max)
      : 0,
  }));

  return (
    <div className={`panel relative overflow-hidden p-5 ${className ?? ""}`}>
      <header className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            Score Breakdown
          </h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {score?.score ?? "—"}/100
        </span>
      </header>

      <div className="h-[240px] w-full">
        <ResponsiveContainer>
          <RadarChart data={data} outerRadius={86}>
            <PolarGrid stroke="rgba(56,225,255,0.15)" />
            <PolarAngleAxis
              dataKey="metric"
              tick={{ fill: "#7C8699", fontSize: 10, fontFamily: "var(--font-mono)" }}
            />
            <PolarRadiusAxis
              angle={90}
              tick={false}
              axisLine={false}
              domain={[0, 1]}
            />
            <Radar
              dataKey="pct"
              stroke="#38E1FF"
              strokeWidth={1.5}
              fill="#38E1FF"
              fillOpacity={0.25}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 space-y-1.5">
        {data.map((d, i) => (
          <motion.div
            key={d.metric}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04 }}
            className="flex items-center justify-between rounded border border-border/40 bg-white/[0.02] px-2.5 py-1.5"
          >
            <span className="text-xs text-foreground/80">{d.metric}</span>
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-24 overflow-hidden rounded-full bg-white/[0.05]">
                <div
                  className="h-full rounded-full bg-primary shadow-glow"
                  style={{ width: `${d.pct * 100}%` }}
                />
              </div>
              <span className="font-mono text-[11px] tabular-nums text-foreground">
                {d.value}/{d.full}
              </span>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
