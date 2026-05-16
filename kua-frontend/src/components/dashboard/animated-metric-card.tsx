"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface AnimatedMetricCardProps {
  label: string;
  value: string;
  delta?: string;
  tone?: "default" | "accent" | "warning" | "danger";
  className?: string;
}

export function AnimatedMetricCard({
  label,
  value,
  delta,
  tone = "default",
  className,
}: AnimatedMetricCardProps) {
  const color =
    tone === "accent"
      ? "text-accent"
      : tone === "warning"
      ? "text-kua-amber"
      : tone === "danger"
      ? "text-destructive"
      : "text-foreground";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.45 }}
      className={cn(
        "panel relative overflow-hidden p-4 transition-all",
        className
      )}
    >
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
      <div className="tactical-mono">{label}</div>
      <div className={cn("mt-1 font-mono text-xl font-semibold tabular-nums", color)}>
        {value}
      </div>
      {delta && (
        <div className="mt-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {delta}
        </div>
      )}
    </motion.div>
  );
}
