"use client";

import {
  ArrowUpRight,
  Building2,
  ChevronUp,
  Forklift,
  LinkIcon,
  MapPin,
  PanelTopOpen,
  Ruler,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { metersLabel, num } from "@/lib/format";
import type { PropertyRecord } from "@/lib/api/types";

interface PropertyMetadataProps {
  property: PropertyRecord;
  className?: string;
}

export function PropertyMetadata({ property, className }: PropertyMetadataProps) {
  const rows: { icon: any; label: string; value: React.ReactNode }[] = [
    { icon: MapPin, label: "Address", value: property.address || "—" },
    { icon: MapPin, label: "Neighbourhood", value: property.neighbourhood || "—" },
    { icon: Ruler, label: "GBA", value: metersLabel(property.gba_m2 ?? null) },
    { icon: ChevronUp, label: "Ceiling height", value: property.ceiling_height ? `${num(property.ceiling_height)} m` : "—" },
    { icon: Forklift, label: "Loading access", value: property.loading_access ? "Yes" : "No / unconfirmed" },
    { icon: PanelTopOpen, label: "Access type", value: property.access_type || "—" },
    { icon: Building2, label: "Building type", value: property.building_type || "—" },
    { icon: Building2, label: "Floor level", value: property.floor_level || "—" },
  ];

  return (
    <div className={`panel p-5 ${className ?? ""}`}>
      <header className="mb-3 flex items-center justify-between border-b border-border/60 pb-3">
        <h3 className="text-sm font-semibold text-foreground">
          Property Metadata
        </h3>
        {property.listing_url && (
          <a
            href={property.listing_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-primary hover:underline"
          >
            <LinkIcon className="h-3 w-3" /> Source listing
            <ArrowUpRight className="h-3 w-3" />
          </a>
        )}
      </header>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {rows.map((r) => {
          const Icon = r.icon;
          return (
            <div
              key={r.label}
              className="flex items-start gap-3 rounded border border-border/40 bg-white/[0.02] p-2.5"
            >
              <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                  {r.label}
                </div>
                <div className="truncate text-sm text-foreground">
                  {r.value}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {property.description && (
        <div className="mt-4 border-t border-border/60 pt-3">
          <div className="mb-1 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
            Description
          </div>
          <p className="text-sm leading-relaxed text-foreground/80">
            {property.description}
          </p>
        </div>
      )}

      {property.current_use && (
        <div className="mt-3 flex items-center gap-2">
          <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
            Current use
          </span>
          <Badge variant="outline">{property.current_use}</Badge>
        </div>
      )}
    </div>
  );
}
