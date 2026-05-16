"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { AnimatedCounter } from "@/components/common/animated-counter";
import { cn } from "@/lib/utils";

interface KpiWidgetProps {
  label: string;
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  delta?: number;        // 0.024 = +2.4%
  format?: (n: number) => string;
  icon?: React.ComponentType<{ className?: string }>;
  glow?: "cyan" | "neon" | "rose" | "none";
  spark?: number[];
  index?: number;
  className?: string;
}

export function KpiWidget({
  label,
  value,
  prefix,
  suffix,
  decimals,
  delta,
  format,
  icon: Icon,
  glow = "cyan",
  spark,
  index = 0,
  className,
}: KpiWidgetProps) {
  const glowClass =
    glow === "cyan"
      ? "hover:shadow-glow"
      : glow === "neon"
      ? "hover:shadow-glow-neon"
      : glow === "rose"
      ? "hover:shadow-glow-rose"
      : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.5,
        delay: Math.min(index * 0.06, 0.5),
        ease: [0.16, 1, 0.3, 1],
      }}
      className={cn(
        "group panel relative overflow-hidden p-5 transition-all hover:border-primary/40",
        glowClass,
        className
      )}
    >
      <div className="pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full bg-primary/10 opacity-0 blur-3xl transition-opacity group-hover:opacity-100" />

      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <div className="tactical-mono">{label}</div>
          <div className="font-display text-3xl font-semibold tracking-tight text-foreground">
            <AnimatedCounter
              value={value}
              prefix={prefix}
              suffix={suffix}
              decimals={decimals}
              format={format}
            />
          </div>
        </div>
        {Icon && (
          <div className="rounded-md border border-primary/30 bg-primary/[0.06] p-2">
            <Icon className="h-4 w-4 text-primary" />
          </div>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between">
        {delta != null && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 font-mono text-[10px] uppercase tracking-widest",
              delta >= 0 ? "text-accent" : "text-destructive"
            )}
          >
            {delta >= 0 ? (
              <ArrowUpRight className="h-3 w-3" />
            ) : (
              <ArrowDownRight className="h-3 w-3" />
            )}
            {(Math.abs(delta) * 100).toFixed(1)}% vs prev
          </span>
        )}
        {spark && spark.length > 1 && <Sparkline data={spark} />}
      </div>
    </motion.div>
  );
}

function Sparkline({ data }: { data: number[] }) {
  const w = 80;
  const h = 24;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = w / (data.length - 1);
  const path = data
    .map((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / range) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="opacity-80">
      <defs>
        <linearGradient id="sparkfill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(56,225,255,0.45)" />
          <stop offset="100%" stopColor="rgba(56,225,255,0)" />
        </linearGradient>
      </defs>
      <path d={`${path} L${w},${h} L0,${h} Z`} fill="url(#sparkfill)" />
      <path d={path} stroke="#38E1FF" strokeWidth={1.4} fill="none" />
    </svg>
  );
}
