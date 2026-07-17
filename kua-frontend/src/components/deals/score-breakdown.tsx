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
import { Brain, ShieldAlert, ShieldCheck } from "lucide-react";
import type { DealScore, StorageSubScores } from "@/lib/api/types";

interface ScoreBreakdownProps {
  score?: DealScore | null;
  className?: string;
}

// v3: six independent dimensions, each on a 0–100 scale.
const FIELDS: { key: keyof StorageSubScores; label: string }[] = [
  { key: "financial_return", label: "Financial" },
  { key: "operational_feasibility", label: "Operational" },
  { key: "location_demand", label: "Location" },
  { key: "physical_suitability", label: "Physical" },
  { key: "risk", label: "Risk" },
  { key: "data_confidence", label: "Confidence" },
];

function resolveSubScores(score?: DealScore | null): StorageSubScores {
  if (score?.sub_scores) return score.sub_scores;
  // Legacy fallback (pre-v3 analyses): map old auto_scores onto the new axes.
  const a = score?.auto_scores as Record<string, number> | undefined;
  return {
    financial_return: a?.economics_score ?? null,
    operational_feasibility: a?.operational_score ?? a?.building_score ?? null,
    location_demand: a?.location_score ?? null,
    physical_suitability: a?.building_score ?? null,
    risk: a?.risk_score ?? null,
    data_confidence: a?.certainty_score ?? null,
  };
}

export function ScoreBreakdown({ score, className }: ScoreBreakdownProps) {
  const sub = resolveSubScores(score);
  const data = FIELDS.map((f) => {
    const value = Number(sub[f.key] ?? 0) || 0;
    return { metric: f.label, value, pct: Math.min(1, value / 100) };
  });

  const gates = score?.gates ?? [];
  const failed = gates.filter((g) => g.mandatory && !g.passed);
  const confidence = score?.confidence?.pct ?? null;
  const verdictDetail = score?.verdict_detail ?? null;
  const conditions = score?.conditions ?? [];

  return (
    <div className={`panel relative overflow-hidden p-5 ${className ?? ""}`}>
      <header className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">Score Breakdown</h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {score?.score ?? "—"}/100
        </span>
      </header>

      {(verdictDetail || confidence != null || score?.scoring_version) && (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px]">
          {verdictDetail && (
            <span className="rounded bg-muted/60 px-2 py-0.5 font-mono uppercase tracking-wide text-muted-foreground">
              {verdictDetail.replace(/_/g, " ")}
            </span>
          )}
          {confidence != null && (
            <span
              className={
                confidence >= 70
                  ? "rounded bg-emerald-500/10 px-2 py-0.5 text-emerald-500"
                  : confidence < 45
                    ? "rounded bg-destructive/10 px-2 py-0.5 text-destructive"
                    : "rounded bg-kua-amber/10 px-2 py-0.5 text-kua-amber"
              }
            >
              Confidence {Math.round(confidence)}%
            </span>
          )}
          {score?.scoring_version && (
            <span className="ml-auto font-mono text-[10px] text-muted-foreground">
              {score.scoring_version}
            </span>
          )}
        </div>
      )}

      <div className="h-[240px] w-full">
        <ResponsiveContainer>
          <RadarChart data={data} outerRadius={86}>
            <PolarGrid stroke="rgba(56,225,255,0.15)" />
            <PolarAngleAxis
              dataKey="metric"
              tick={{ fill: "#7C8699", fontSize: 10, fontFamily: "var(--font-mono)" }}
            />
            <PolarRadiusAxis angle={90} tick={false} axisLine={false} domain={[0, 1]} />
            <Radar dataKey="pct" stroke="#38E1FF" strokeWidth={1.5} fill="#38E1FF" fillOpacity={0.25} />
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
                {Math.round(d.value)}/100
              </span>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Hard gates — what prevents / permits approval */}
      {gates.length > 0 && (
        <div className="mt-4 border-t border-border/60 pt-3">
          <div className="mb-2 flex items-center gap-2">
            {failed.length === 0 ? (
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
            ) : (
              <ShieldAlert className="h-3.5 w-3.5 text-destructive" />
            )}
            <h4 className="text-xs font-semibold text-foreground">
              Hard Gates {failed.length > 0 ? `— ${failed.length} failing` : "— all passing"}
            </h4>
          </div>
          <div className="space-y-1">
            {gates.map((g) => (
              <div key={g.name} className="flex items-start gap-2 text-[11px] leading-snug">
                <span className={g.passed ? "text-emerald-500" : "text-destructive"}>
                  {g.passed ? "✓" : "✕"}
                </span>
                <span className={g.passed ? "text-muted-foreground" : "text-foreground"}>
                  {g.message}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {conditions.length > 0 && (
        <div className="mt-3 border-t border-border/60 pt-3">
          <h4 className="mb-1 text-xs font-semibold text-foreground">
            Conditions for Approval
          </h4>
          <ul className="space-y-1">
            {conditions.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-[11px] text-muted-foreground">
                <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-kua-amber" />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
