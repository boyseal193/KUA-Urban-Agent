"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { LaundryDealStatus } from "@/lib/api";

const STATUS_META: Record<
  string,
  { label: string; color: string; chipClass: string }
> = {
  approved_candidate: {
    label: "APPROVED",
    color: "#A78BFA",
    chipClass: "border-violet-400/40 bg-violet-400/10 text-violet-300",
  },
  manual_review: {
    label: "MANUAL REVIEW",
    color: "#38BDF8",
    chipClass: "border-sky-400/40 bg-sky-400/10 text-sky-300",
  },
  rejected: {
    label: "REJECT",
    color: "#FB7185",
    chipClass: "border-rose-400/40 bg-rose-400/10 text-rose-300",
  },
  extraction_failed: {
    label: "EXTRACTION FAILED",
    color: "#FACC15",
    chipClass: "border-amber-400/40 bg-amber-400/10 text-amber-200",
  },
  deleted: {
    label: "DELETED",
    color: "#9CA3AF",
    chipClass: "border-zinc-500/40 bg-zinc-500/10 text-zinc-400",
  },
};

export function laundryStatusMeta(status?: LaundryDealStatus | null) {
  return STATUS_META[status ?? ""] ?? STATUS_META.manual_review;
}

export function LaundryStatusBadge({
  status,
  className,
}: {
  status?: LaundryDealStatus | null;
  className?: string;
}) {
  const meta = laundryStatusMeta(status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest",
        meta.chipClass,
        className,
      )}
    >
      <span
        className="badge-dot"
        style={{ background: meta.color }}
      />
      {meta.label}
    </span>
  );
}
