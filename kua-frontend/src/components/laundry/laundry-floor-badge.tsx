"use client";

import { cn } from "@/lib/utils";
import type { LaundryProperty } from "@/lib/api";
import { floorStatusMeta } from "@/lib/laundry-pipeline-utils";

export function LaundryFloorBadge({
  deal,
  className,
  compact = false,
}: {
  deal: Pick<LaundryProperty, "ground_floor" | "ground_floor_status" | "ground_floor_verification">;
  className?: string;
  compact?: boolean;
}) {
  const meta = floorStatusMeta(deal);

  const toneClass =
    meta.tone === "positive"
      ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-200"
      : meta.tone === "warning"
        ? "border-amber-400/35 bg-amber-400/10 text-amber-100"
        : "border-sky-400/35 bg-sky-400/10 text-sky-200";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 font-mono uppercase tracking-widest",
        compact ? "text-[9px]" : "text-[10px]",
        toneClass,
        className,
      )}
      title={meta.label}
    >
      <span className="badge-dot" style={{ background: meta.color }} />
      {compact ? meta.shortLabel : meta.label}
    </span>
  );
}
