"use client";

import Link from "next/link";
import { ExternalLink, FileText, MapPin } from "lucide-react";

import { LaundryScoreBadge } from "./laundry-score-badge";
import { LaundryStatusBadge } from "./laundry-status";
import { Button } from "@/components/ui/button";
import { moneyCompact, metersLabel } from "@/lib/format";
import type { LaundryProperty } from "@/lib/api";

interface Props {
  property: LaundryProperty;
  index?: number;
}

export function LaundryScanListingCard({ property, index = 0 }: Props) {
  if (!property?.id) return null;

  const acq = property.acquisition_type === "rent" ? "RENT" : "BUY";
  const price =
    property.acquisition_type === "rent"
      ? `${moneyCompact(property.asking_rent_month ?? null)}/mo`
      : moneyCompact(property.asking_price ?? null);
  const risks = property.risk_flags ?? [];

  return (
    <article className="panel overflow-hidden border border-border/60 bg-card/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <LaundryScoreBadge score={property.score ?? null} size="md" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <LaundryStatusBadge status={property.deal_status} />
              <span className="rounded border border-border/60 bg-card/60 px-1.5 py-px font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                {acq}
              </span>
              <span className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                #{index + 1}
              </span>
            </div>
            <h3 className="mt-1 truncate font-display text-sm font-semibold text-foreground">
              {property.address || property.neighbourhood || "Untitled listing"}
            </h3>
            <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <MapPin className="h-3 w-3 flex-shrink-0" />
              <span className="truncate">
                {property.neighbourhood || "—"} · {property.city || "—"}
              </span>
            </p>
          </div>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-border/60 pt-4 text-xs sm:grid-cols-4">
        <div>
          <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Size</dt>
          <dd className="mt-1 font-mono tabular-nums">{metersLabel(property.floor_area_m2 ?? null)}</dd>
        </div>
        <div>
          <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            {acq === "RENT" ? "Rent" : "Price"}
          </dt>
          <dd className="mt-1 font-mono tabular-nums">{price}</dd>
        </div>
        <div>
          <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">EBITDA</dt>
          <dd className="mt-1 font-mono tabular-nums">{moneyCompact(property.ebitda_eur ?? null)}</dd>
        </div>
        <div>
          <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Verdict</dt>
          <dd className="mt-1 truncate">{property.verdict || "—"}</dd>
        </div>
      </dl>

      {risks.length > 0 && (
        <ul className="mt-3 list-disc pl-4 text-[11px] text-amber-200/90">
          {risks.slice(0, 3).map((flag, i) => (
            <li key={i}>{flag}</li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap gap-2 border-t border-border/60 pt-3">
        <Button asChild variant="tactical" size="sm" className="bg-violet-500/10 text-violet-300 hover:bg-violet-500/20">
          <Link href={`/laundry/property/${property.id}`}>
            <FileText className="h-3.5 w-3.5" /> Open memo
          </Link>
        </Button>
        {property.listing_url && (
          <Button asChild variant="ghost" size="sm">
            <a href={property.listing_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-3.5 w-3.5" /> Original listing
            </a>
          </Button>
        )}
      </div>
    </article>
  );
}
