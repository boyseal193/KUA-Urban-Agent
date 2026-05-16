"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { pct } from "@/lib/format";
import { cn } from "@/lib/utils";

interface YieldWidgetProps {
  label: string;
  value: number | null | undefined;
  comparison?: number | null | undefined; // optional baseline
  className?: string;
  size?: "sm" | "md";
}

export function YieldWidget({
  label,
  value,
  comparison,
  className,
  size = "md",
}: YieldWidgetProps) {
  const v = typeof value === "number" ? value : null;
  const baseline = typeof comparison === "number" ? comparison : null;

  const tone =
    v == null
      ? "text-muted-foreground"
      : v >= 0.12
      ? "text-accent"
      : v >= 0.08
      ? "text-primary"
      : v >= 0.06
      ? "text-kua-amber"
      : "text-destructive";

  const trend =
    v != null && baseline != null
      ? v - baseline
      : null;

  return (
    <div className={cn("space-y-1", className)}>
      <div className="tactical-mono">{label}</div>
      <div className="flex items-baseline gap-2">
        <span
          className={cn(
            "font-mono font-semibold tabular-nums",
            size === "md" ? "text-xl" : "text-sm",
            tone
          )}
        >
          {pct(v)}
        </span>
        {trend != null && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 font-mono text-[10px]",
              trend > 0 ? "text-accent" : "text-destructive"
            )}
          >
            {trend > 0 ? (
              <TrendingUp className="h-3 w-3" />
            ) : (
              <TrendingDown className="h-3 w-3" />
            )}
            {pct(Math.abs(trend))}
          </span>
        )}
      </div>
    </div>
  );
}
