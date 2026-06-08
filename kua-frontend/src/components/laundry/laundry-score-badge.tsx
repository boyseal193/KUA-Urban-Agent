"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface LaundryScoreBadgeProps {
  score?: number | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function laundryTier(score?: number | null) {
  if (score == null) return { label: "—", color: "#64748B" };
  if (score >= 75) return { label: "CORE", color: "#A78BFA" };
  if (score >= 50) return { label: "REVIEW", color: "#38BDF8" };
  return { label: "REJECT", color: "#FB7185" };
}

export function LaundryScoreBadge({
  score,
  size = "md",
  className,
}: LaundryScoreBadgeProps) {
  const tier = laundryTier(score);
  const dim =
    size === "sm" ? "h-9 w-9 text-xs" : size === "lg" ? "h-14 w-14 text-base" : "h-11 w-11 text-sm";
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-md border font-mono font-semibold tabular-nums",
        dim,
        className,
      )}
      style={{
        borderColor: `${tier.color}66`,
        backgroundColor: `${tier.color}1A`,
        color: tier.color,
      }}
      aria-label={`Score ${score ?? "n/a"} of 100`}
    >
      {score != null ? score : "—"}
      <span className="text-[8px] tracking-widest opacity-80">{tier.label}</span>
    </div>
  );
}
