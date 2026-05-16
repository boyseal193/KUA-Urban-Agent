"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { scoreTier } from "@/lib/constants";

interface ScoreBadgeProps {
  score?: number | null;
  size?: "sm" | "md" | "lg";
  showTier?: boolean;
  className?: string;
}

export function ScoreBadge({
  score,
  size = "md",
  showTier = true,
  className,
}: ScoreBadgeProps) {
  const tier = scoreTier(score);
  const dim =
    size === "sm" ? 36 : size === "lg" ? 80 : 56;
  const stroke = size === "sm" ? 3 : size === "lg" ? 5 : 4;
  const r = (dim - stroke) / 2;
  const c = 2 * Math.PI * r;
  const value = Math.max(0, Math.min(100, score ?? 0));
  const dash = (value / 100) * c;

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        className="relative inline-flex items-center justify-center"
        style={{ width: dim, height: dim }}
      >
        <svg
          width={dim}
          height={dim}
          viewBox={`0 0 ${dim} ${dim}`}
          className="-rotate-90"
        >
          <circle
            cx={dim / 2}
            cy={dim / 2}
            r={r}
            fill="transparent"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={stroke}
          />
          <motion.circle
            cx={dim / 2}
            cy={dim / 2}
            r={r}
            fill="transparent"
            stroke={tier.color}
            strokeLinecap="round"
            strokeWidth={stroke}
            strokeDasharray={c}
            initial={{ strokeDashoffset: c }}
            whileInView={{ strokeDashoffset: c - dash }}
            transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
            viewport={{ once: true }}
            style={{
              filter: `drop-shadow(0 0 6px ${tier.color}AA)`,
            }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span
            className={cn(
              "font-mono font-semibold tabular-nums",
              size === "sm" && "text-[10px]",
              size === "md" && "text-sm",
              size === "lg" && "text-xl"
            )}
            style={{ color: tier.color }}
          >
            {score == null ? "—" : Math.round(score)}
          </span>
        </div>
      </div>
      {showTier && (
        <div className="leading-tight">
          <div
            className="font-mono text-[10px] uppercase tracking-[0.18em]"
            style={{ color: tier.color }}
          >
            {tier.label}
          </div>
          <div className="text-[10px] text-muted-foreground">SCORE / 100</div>
        </div>
      )}
    </div>
  );
}
