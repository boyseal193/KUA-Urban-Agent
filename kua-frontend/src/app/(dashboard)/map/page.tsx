"use client";

import { PageHeader } from "@/components/common/page-header";
import { PropertyMap } from "@/components/map/property-map-dynamic";
import { FilterSidebar } from "@/components/filters/filter-sidebar";
import { StatusPill } from "@/components/common/status-pill";

import {
  useApprovedDeals,
  useManualReviewDeals,
  useRejectedDeals,
} from "@/hooks/use-deals";
import { useFilters } from "@/hooks/use-filters";
import type { PropertyRecord } from "@/lib/api/types";

export default function MapPage() {
  const approved = useApprovedDeals(200);
  const manual = useManualReviewDeals(200);
  const rejected = useRejectedDeals(200);
  const filters = useFilters();

  const filterDeal = (d: PropertyRecord) => {
    if (filters.district && d.neighbourhood && !d.neighbourhood
      .toLowerCase()
      .includes(filters.district.toLowerCase())) return false;
    const price = Number(d.asking_price) || 0;
    if (price < filters.priceRange[0] || price > filters.priceRange[1]) return false;
    const m2 = Number(d.gba_m2) || 0;
    if (m2 < filters.m2Range[0] || m2 > filters.m2Range[1]) return false;
    if (filters.status !== "all" && d.deal_status !== filters.status) return false;
    return true;
  };

  const deals = [
    ...(approved.data ?? []),
    ...(manual.data ?? []),
    ...(rejected.data ?? []),
  ].filter(filterDeal);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="OPS · TACTICAL MAP"
        title="Tactical Map"
        subtitle="All scanned properties plotted across Barcelona. Color-coded by verdict, clustered at zoom-out."
        rightSlot={
          <>
            <StatusPill label={`${deals.length} ASSETS`} color="#38E1FF" />
            <StatusPill label="CARTO · DARK MATTER" color="#7CFAB3" pulse={false} />
          </>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        <FilterSidebar />
        <PropertyMap deals={deals} />
      </div>
    </div>
  );
}
