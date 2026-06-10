"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight, MapPin, Ruler, WashingMachine, Wind } from "lucide-react";

import { cn } from "@/lib/utils";
import { moneyCompact, metersLabel } from "@/lib/format";
import { LaundryScoreBadge } from "./laundry-score-badge";
import { LaundryStatusBadge } from "./laundry-status";
import type { LaundryProperty } from "@/lib/api";

interface Props {
  deal: LaundryProperty;
  index?: number;
  compact?: boolean;
  className?: string;
  selectable?: boolean;
  selected?: boolean;
  onSelectToggle?: (id: string) => void;
}

export function LaundryDealCard({
  deal,
  index = 0,
  compact = false,
  className,
  selectable = false,
  selected = false,
  onSelectToggle,
}: Props) {
  if (!deal?.id) return null;

  const acq = deal.acquisition_type === "rent" ? "RENT" : "BUY";
  const price =
    deal.acquisition_type === "rent"
      ? `${moneyCompact(deal.asking_rent_month ?? null)}/mo`
      : moneyCompact(deal.asking_price ?? null);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.4,
        delay: Math.min(index * 0.04, 0.4),
        ease: [0.16, 1, 0.3, 1],
      }}
      whileHover={{ y: -2 }}
      className={cn(
        "group relative panel overflow-hidden transition-all hover:border-violet-400/40 hover:shadow-glow",
        selected && "border-emerald-400/50 ring-1 ring-emerald-400/30",
        className,
      )}
    >
      {selectable && (
        <button
          type="button"
          aria-pressed={selected}
          aria-label={selected ? "Deselect deal" : "Select deal"}
          className="absolute left-3 top-3 z-10 rounded border border-border/60 bg-card/90 p-1"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onSelectToggle?.(deal.id);
          }}
        >
          <span
            className={cn(
              "block h-3.5 w-3.5 rounded-sm border",
              selected ? "border-emerald-300 bg-emerald-400" : "border-muted-foreground/40",
            )}
          />
        </button>
      )}
      <Link href={`/laundry/property/${deal.id}`} className={cn("block p-4", selectable && "pl-10")}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <LaundryScoreBadge score={deal.score ?? null} size={compact ? "sm" : "md"} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <LaundryStatusBadge status={deal.deal_status} />
                <span className="rounded border border-border/60 bg-card/60 px-1.5 py-px font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                  {acq}
                </span>
                <span className="rounded border border-border/60 bg-card/60 px-1.5 py-px font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                  {(deal.property_type || "—").replace(/_/g, " ")}
                </span>
              </div>
              <div className="mt-1 truncate font-display text-sm font-semibold text-foreground">
                {deal.address || deal.neighbourhood || "Untitled property"}
              </div>
              <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <MapPin className="h-3 w-3" />
                <span className="truncate">
                  {deal.neighbourhood || "—"} · {deal.city || "—"}
                </span>
              </div>
            </div>
          </div>
          <ArrowUpRight className="h-4 w-4 text-muted-foreground opacity-0 transition group-hover:opacity-100 group-hover:text-violet-300" />
        </div>

        <div
          className={cn(
            "mt-4 grid gap-3 border-t border-border/60 pt-4",
            compact ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-4",
          )}
        >
          <Stat icon={Ruler} label="Area" value={metersLabel(deal.floor_area_m2 ?? null)} />
          <Stat icon={WashingMachine} label="Washers" value={deal.washer_count ?? "—"} />
          <Stat icon={Wind} label="Dryers" value={deal.dryer_count ?? "—"} />
          <Stat icon={Ruler} label={acq === "RENT" ? "Rent" : "Asking"} value={price} />
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-3 font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
          <span>ID · {deal.id.slice(0, 8)}</span>
          <span>{deal.verdict || "—"}</span>
          <span className="text-violet-300 group-hover:underline">OPEN MEMO</span>
        </div>
      </Link>
    </motion.div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 tactical-mono">
        <Icon className="h-3 w-3" /> {label}
      </div>
      <div className="font-mono text-sm font-medium tabular-nums text-foreground">{value}</div>
    </div>
  );
}
