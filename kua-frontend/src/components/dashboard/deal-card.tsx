"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowUpRight,
  Building2,
  Gauge,
  MapPin,
  Ruler,
  Timer,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ScoreBadge } from "./score-badge";
import { DealStatusIndicator } from "./deal-status-indicator";
import { YieldWidget } from "./yield-widget";
import { DeletePropertyButton } from "@/components/properties/delete-property-button";
import { moneyCompact, yearsLabel, metersLabel } from "@/lib/format";
import { verdictMeta } from "@/lib/constants";
import { useStaleProperties } from "@/lib/stale-properties";
import { cn } from "@/lib/utils";

import type { PropertyRecord, AnalysisResult, DealEconomics } from "@/lib/api/types";

interface DealCardProps {
  deal: PropertyRecord;
  /** When the card displays a fresh scan result we have the full economics blob */
  enriched?: AnalysisResult | null;
  index?: number;
  compact?: boolean;
  className?: string;
}

export function DealCard({
  deal,
  enriched,
  index = 0,
  compact = false,
  className,
}: DealCardProps) {
  const { isStale } = useStaleProperties();

  // If the property has been deleted out-of-band (admin, another tab, etc.),
  // refuse to render — the card would be a dead link.
  if (!deal?.id || isStale(deal.id)) {
    return null;
  }

  const verdict = verdictMeta(deal.verdict);
  const econ: Partial<DealEconomics> = enriched?.economics ?? {};
  const flags = enriched?.score?.due_diligence_flags ?? [];
  const dealKiller =
    enriched?.score?.deal_killer ?? null;
  const failedGates = enriched?.score?.gate_failures ?? [];
  const confidencePct = enriched?.score?.confidence?.pct ?? null;
  const verdictDetail = enriched?.score?.verdict_detail ?? null;

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
        "group relative panel overflow-hidden transition-all hover:border-primary/40 hover:shadow-glow",
        className
      )}
    >
      {/* hover sweep */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />

      {/* delete affordance — overlay so it doesn't trip the card link */}
      <div className="absolute right-2 top-2 z-20 opacity-0 transition-opacity group-hover:opacity-100">
        <DeletePropertyButton
          propertyId={deal.id}
          label={deal.address || deal.neighbourhood || undefined}
          variant="icon"
        />
      </div>

      <Link href={`/deals/${deal.id}`} className="block p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <ScoreBadge score={deal.score ?? null} size={compact ? "sm" : "md"} showTier={false} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <DealStatusIndicator status={deal.deal_status ?? null} />
                <Badge className={verdict.chipClass}>
                  {verdict.label}
                </Badge>
              </div>
              <div className="mt-1 truncate font-display text-sm font-semibold text-foreground">
                {deal.address || deal.neighbourhood || "Untitled property"}
              </div>
              <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <MapPin className="h-3 w-3" />
                <span className="truncate">
                  {deal.neighbourhood || "—"} · {deal.city || "Barcelona"}
                </span>
              </div>
            </div>
          </div>
          <ArrowUpRight className="h-4 w-4 text-muted-foreground opacity-0 transition group-hover:opacity-100 group-hover:text-primary" />
        </div>

        {/* Stats grid */}
        <div
          className={cn(
            "mt-4 grid gap-3 border-t border-border/60 pt-4",
            compact ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-4"
          )}
        >
          <Stat
            icon={Gauge}
            label="Asking"
            value={moneyCompact(deal.asking_price ?? null)}
          />
          <Stat
            icon={Ruler}
            label="GBA"
            value={metersLabel(deal.gba_m2 ?? null)}
          />
          {!compact && (
            <YieldWidget
              size="sm"
              label="True Yield"
              value={econ.true_ebitda_yield ?? null}
            />
          )}
          {!compact && (
            <Stat
              icon={Timer}
              label="Payback"
              value={yearsLabel(econ.true_payback_years ?? null)}
            />
          )}
          {compact && (
            <Stat
              icon={Building2}
              label="Type"
              value={deal.building_type || "—"}
            />
          )}
        </div>

        {/* v3 gate/confidence strip — only for enriched (fresh) results */}
        {!compact && (failedGates.length > 0 || confidencePct != null || verdictDetail) && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border/60 pt-3">
            {verdictDetail && (
              <Badge className="bg-muted/60 text-[10px] uppercase tracking-wide text-muted-foreground">
                {verdictDetail.replace(/_/g, " ")}
              </Badge>
            )}
            {confidencePct != null && (
              <Badge
                className={cn(
                  "text-[10px]",
                  confidencePct >= 70
                    ? "bg-emerald-500/10 text-emerald-500"
                    : confidencePct < 45
                      ? "bg-destructive/10 text-destructive"
                      : "bg-kua-amber/10 text-kua-amber"
                )}
              >
                Confidence {Math.round(confidencePct)}%
              </Badge>
            )}
            {failedGates.slice(0, 3).map((g) => (
              <Badge key={g} className="bg-destructive/10 text-[10px] text-destructive">
                ✕ {g.replace(/_/g, " ")}
              </Badge>
            ))}
            {failedGates.length > 3 && (
              <span className="text-[10px] text-muted-foreground">
                +{failedGates.length - 3} more gates
              </span>
            )}
          </div>
        )}

        {/* Flags / killer */}
        {(dealKiller || flags.length > 0) && !compact && (
          <div className="mt-3 space-y-1.5 border-t border-border/60 pt-3">
            {dealKiller && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/[0.06] px-2.5 py-1.5">
                <AlertTriangle className="mt-px h-3 w-3 shrink-0 text-destructive" />
                <p className="text-[11px] leading-snug text-destructive">
                  {dealKiller}
                </p>
              </div>
            )}
            {flags.slice(0, 2).map((f, i) => (
              <div
                key={i}
                className="flex items-start gap-2 text-[11px] leading-snug text-muted-foreground"
              >
                <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-kua-amber" />
                <span className="line-clamp-2">{f}</span>
              </div>
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-3 font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
          <span>ID · {deal.id?.slice(0, 8) ?? "—"}</span>
          <span>{(deal as any).source ?? "AUTO"}</span>
          <span className="text-primary group-hover:underline">OPEN MEMO</span>
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
      <div className="font-mono text-sm font-medium tabular-nums text-foreground">
        {value}
      </div>
    </div>
  );
}
