"use client";

import Link from "next/link";
import { AlertTriangle, ExternalLink, FileText, MapPin } from "lucide-react";

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

  const isExtractionFailed = property.deal_status === "extraction_failed";
  const acq = property.acquisition_type === "rent" ? "RENT" : property.acquisition_type === "buy" ? "BUY" : "—";
  const price =
    property.acquisition_type === "rent"
      ? `${moneyCompact(property.asking_rent_month ?? null)}/mo`
      : moneyCompact(property.asking_price ?? null);
  const risks = property.risk_flags ?? [];
  const displayTitle =
    property.address ||
    (property as LaundryProperty & { title?: string }).title ||
    property.neighbourhood ||
    (isExtractionFailed ? "Listing (extraction failed)" : "Untitled listing");

  return (
    <article
      className={`panel overflow-hidden border bg-card/40 p-4 ${
        isExtractionFailed ? "border-amber-500/40" : "border-border/60"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          {!isExtractionFailed && <LaundryScoreBadge score={property.score ?? null} size="md" />}
          {isExtractionFailed && (
            <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-md border border-amber-500/40 bg-amber-500/10">
              <AlertTriangle className="h-4 w-4 text-amber-300" />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <LaundryStatusBadge status={property.deal_status} />
              {!isExtractionFailed && (
                <span className="rounded border border-border/60 bg-card/60 px-1.5 py-px font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                  {acq}
                </span>
              )}
              <span className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                #{index + 1}
              </span>
            </div>
            <h3 className="mt-1 truncate font-display text-sm font-semibold text-foreground">
              {displayTitle}
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

      {isExtractionFailed ? (
        <div className="mt-4 space-y-2 border-t border-border/60 pt-4 text-xs text-muted-foreground">
          <p>
            Detail page could not be scraped or parsed. The listing URL was saved so you can
            open it manually.
          </p>
          {property.verdict && (
            <p className="font-mono text-[10px] text-amber-200/90">{property.verdict}</p>
          )}
        </div>
      ) : (
        <>
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
        </>
      )}

      <div className="mt-4 flex flex-wrap gap-2 border-t border-border/60 pt-3">
        {!isExtractionFailed && (
          <Button asChild variant="tactical" size="sm" className="bg-violet-500/10 text-violet-300 hover:bg-violet-500/20">
            <Link href={`/laundry/property/${property.id}`}>
              <FileText className="h-3.5 w-3.5" /> Open memo
            </Link>
          </Button>
        )}
        {property.listing_url && (
          <Button asChild variant={isExtractionFailed ? "tactical" : "ghost"} size="sm">
            <a href={property.listing_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-3.5 w-3.5" /> Original listing
            </a>
          </Button>
        )}
      </div>
    </article>
  );
}
