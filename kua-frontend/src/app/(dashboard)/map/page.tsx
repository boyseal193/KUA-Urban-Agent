"use client";

import { PageHeader } from "@/components/common/page-header";
import { MapDiagnosticsPanel } from "@/components/map/map-diagnostics-panel";
import { PropertyMap } from "@/components/map/property-map-dynamic";
import { FilterSidebar } from "@/components/filters/filter-sidebar";
import { StatusPill } from "@/components/common/status-pill";

import { useTacticalMapMarkers } from "@/hooks/use-map";
import { useFilters } from "@/hooks/use-filters";
import type { PropertyRecord } from "@/lib/api/types";
import type { TacticalMapMarker } from "@/lib/api/map";

function toPropertyRecord(marker: TacticalMapMarker): PropertyRecord {
  return {
    id: marker.id,
    latitude: marker.latitude ?? marker.lat,
    longitude: marker.longitude ?? marker.lng,
    score: marker.score ?? null,
    deal_status: (marker.deal_status as PropertyRecord["deal_status"]) ?? "manual_review",
    address: marker.address ?? null,
    city: marker.city ?? "Barcelona",
    neighbourhood: marker.neighbourhood ?? null,
    verdict: marker.verdict ?? null,
    asking_price: null,
    gba_m2: null,
    status: marker.deal_status ?? "unknown",
  } as PropertyRecord;
}

export default function MapPage() {
  const q = useTacticalMapMarkers(500, "all");
  const filters = useFilters();

  const markers = q.data?.markers ?? [];
  const diagnostics = q.data?.diagnostics;

  const filterDeal = (d: PropertyRecord) => {
    if (filters.district && d.neighbourhood && !d.neighbourhood
      .toLowerCase()
      .includes(filters.district.toLowerCase())) return false;
    const price = Number(d.asking_price) || 0;
    if (price > 0 && (price < filters.priceRange[0] || price > filters.priceRange[1])) return false;
    const m2 = Number(d.gba_m2) || 0;
    if (m2 > 0 && (m2 < filters.m2Range[0] || m2 > filters.m2Range[1])) return false;
    if (filters.status !== "all" && d.deal_status !== filters.status) return false;
    return true;
  };

  const deals = markers.map(toPropertyRecord).filter(filterDeal);
  const plotted = deals.filter(
    (d) => typeof d.latitude === "number" && typeof d.longitude === "number",
  ).length;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="OPS · TACTICAL MAP"
        title="Tactical Map"
        subtitle="Storage + laundry acquisitions plotted across Barcelona. Missing coordinates are geocoded on load."
        rightSlot={
          <>
            <StatusPill label={`${plotted} ASSETS`} color="#38E1FF" />
            <StatusPill label="STORAGE + LAUNDRY" color="#A78BFA" pulse={false} />
          </>
        }
      />

      <MapDiagnosticsPanel
        diagnostics={diagnostics}
        plotted={plotted}
        total={markers.length}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        <FilterSidebar />
        <PropertyMap
          deals={deals}
          missingCount={(diagnostics?.missing_coordinates ?? 0)}
          totalCount={markers.length}
        />
      </div>
    </div>
  );
}
