"use client";

import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Columns3, FilterIcon, LayoutGrid } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DealCard } from "@/components/dashboard/deal-card";
import { DealTable } from "@/components/dashboard/deal-table";
import { DealRowSkeleton } from "@/components/common/loading-skeleton";
import { FilterSidebar } from "@/components/filters/filter-sidebar";
import { EmptyState } from "@/components/common/empty-state";
import { dealStatusMeta } from "@/lib/constants";

import {
  useApprovedDeals,
  useManualReviewDeals,
  useRejectedDeals,
} from "@/hooks/use-deals";
import { useFilters } from "@/hooks/use-filters";
import type { PropertyRecord } from "@/lib/api/types";

export default function PipelinePage() {
  const approved = useApprovedDeals(120);
  const manual = useManualReviewDeals(120);
  const rejected = useRejectedDeals(120);
  const filters = useFilters();
  const [view, setView] = React.useState<"kanban" | "table">("kanban");

  const filterDeal = React.useCallback(
    (d: PropertyRecord) => {
      if (filters.district && d.neighbourhood && !d.neighbourhood
        .toLowerCase()
        .includes(filters.district.toLowerCase())) return false;
      const price = Number(d.asking_price) || 0;
      if (price < filters.priceRange[0] || price > filters.priceRange[1]) return false;
      const m2 = Number(d.gba_m2) || 0;
      if (m2 < filters.m2Range[0] || m2 > filters.m2Range[1]) return false;
      if (filters.search) {
        const q = filters.search.toLowerCase();
        const blob = [d.address, d.neighbourhood, d.city, d.id]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!blob.includes(q)) return false;
      }
      if (filters.buildingType && (d.building_type || "").toLowerCase() !==
        filters.buildingType.toLowerCase()) return false;
      if (filters.loadingAccess && !d.loading_access) return false;
      if (
        filters.minCeilingHeight != null &&
        (Number(d.ceiling_height) || 0) < filters.minCeilingHeight
      )
        return false;
      return true;
    },
    [filters]
  );

  const columns = [
    {
      key: "approved_candidate",
      title: "Approved",
      data: (approved.data ?? []).filter(filterDeal),
      loading: approved.isLoading,
    },
    {
      key: "manual_review",
      title: "Manual Review",
      data: (manual.data ?? []).filter(filterDeal),
      loading: manual.isLoading,
    },
    {
      key: "rejected",
      title: "Rejected",
      data: (rejected.data ?? []).filter(filterDeal),
      loading: rejected.isLoading,
    },
  ];

  const allDeals = [
    ...(approved.data ?? []),
    ...(manual.data ?? []),
    ...(rejected.data ?? []),
  ].filter(filterDeal);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="OPS · DEAL PIPELINE"
        title="Deal Pipeline"
        subtitle="Kanban-style triage across approved, manual review and rejected acquisitions. Filters apply across all columns."
        rightSlot={
          <Tabs value={view} onValueChange={(v) => setView(v as any)}>
            <TabsList>
              <TabsTrigger value="kanban" className="gap-1.5">
                <Columns3 className="h-3 w-3" /> Kanban
              </TabsTrigger>
              <TabsTrigger value="table" className="gap-1.5">
                <LayoutGrid className="h-3 w-3" /> Table
              </TabsTrigger>
            </TabsList>
          </Tabs>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        <FilterSidebar />

        <div>
          <Tabs value={view}>
            <TabsContent value="kanban" className="mt-0">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                {columns.map((col) => {
                  const meta = dealStatusMeta(col.key);
                  return (
                    <div
                      key={col.key}
                      className="flex flex-col rounded-xl border border-border/60 bg-card/40 backdrop-blur-xl"
                    >
                      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span
                            className="badge-dot"
                            style={{
                              backgroundColor: meta.color,
                              boxShadow: `0 0 8px ${meta.color}`,
                            }}
                          />
                          <h3 className="text-sm font-semibold text-foreground">
                            {col.title}
                          </h3>
                        </div>
                        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                          {col.data.length}
                        </span>
                      </div>
                      <div className="flex max-h-[calc(100vh-300px)] flex-col gap-3 overflow-y-auto p-3">
                        {col.loading ? (
                          <>
                            <DealRowSkeleton />
                            <DealRowSkeleton />
                            <DealRowSkeleton />
                          </>
                        ) : col.data.length === 0 ? (
                          <EmptyState
                            title="Empty column"
                            description="No deals match the current filters."
                            icon={FilterIcon}
                          />
                        ) : (
                          <AnimatePresence>
                            {col.data.map((d, i) => (
                              <motion.div
                                key={d.id}
                                layout
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -4 }}
                              >
                                <DealCard deal={d} index={i} compact />
                              </motion.div>
                            ))}
                          </AnimatePresence>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </TabsContent>

            <TabsContent value="table" className="mt-0">
              <DealTable deals={allDeals} />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
