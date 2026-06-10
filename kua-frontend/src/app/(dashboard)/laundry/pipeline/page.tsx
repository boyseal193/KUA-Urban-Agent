"use client";

import { useMemo, useState } from "react";

import { PageHeader } from "@/components/common/page-header";
import {
  LaundryBulkExportToolbar,
  LaundryPipelineExportToolbar,
} from "@/components/laundry/laundry-export-actions";
import { LaundryPipelineColumn } from "@/components/laundry/laundry-pipeline-column";
import { Button } from "@/components/ui/button";
import { useLaundryPipelineProperties } from "@/hooks/use-laundry";
import type { LaundryProperty } from "@/lib/api";

const COLUMNS = [
  {
    id: "approved",
    title: "Approved",
    accent: "#A78BFA",
    emptyTitle: "No approved deals",
    match: (d: LaundryProperty) => d.deal_status === "approved_candidate",
  },
  {
    id: "review",
    title: "Manual review",
    accent: "#38BDF8",
    emptyTitle: "Manual review queue is empty",
    match: (d: LaundryProperty) => d.deal_status === "manual_review",
  },
  {
    id: "rejected",
    title: "Rejected",
    accent: "#FB7185",
    emptyTitle: "Nothing rejected yet",
    match: (d: LaundryProperty) =>
      d.deal_status === "rejected" && (d.score ?? 0) >= 40,
  },
  {
    id: "failed",
    title: "Failed",
    accent: "#FACC15",
    emptyTitle: "No failed deals",
    match: (d: LaundryProperty) =>
      d.deal_status === "extraction_failed" ||
      (d.deal_status === "rejected" && (d.score ?? 0) < 40),
  },
] as const;

export default function LaundryPipelinePage() {
  const q = useLaundryPipelineProperties(500);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const buckets = useMemo(() => {
    const deals = q.data ?? [];
    return COLUMNS.map((col) => ({
      ...col,
      deals: deals.filter(col.match).sort((a, b) => (b.score ?? 0) - (a.score ?? 0)),
    }));
  }, [q.data]);

  function toggleSelected(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  const totalDeals = buckets.reduce((sum, col) => sum + col.deals.length, 0);

  return (
    <div className="flex min-h-0 flex-col gap-5 pb-6">
      <PageHeader
        eyebrow="LAUNDRY · PIPELINE"
        title="Acquisition Pipeline"
        subtitle={`Institutional underwriting queue · ${totalDeals} active opportunities across all stages.`}
        rightSlot={<LaundryPipelineExportToolbar />}
      />

      <div className="rounded-xl border border-border/70 bg-card/20 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-display text-sm font-semibold text-foreground">Bulk actions</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Select deals for targeted exports, or export entire pipeline segments.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-9 border border-border/60 font-mono text-[10px] uppercase tracking-widest"
              onClick={() => {
                setSelectMode((v) => !v);
                if (selectMode) setSelectedIds([]);
              }}
            >
              {selectMode ? "Cancel selection" : "Select deals"}
            </Button>
            {selectMode && (
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                {selectedIds.length} selected
              </span>
            )}
          </div>
        </div>
        <LaundryBulkExportToolbar selectedIds={selectedIds} />
      </div>

      <div className="flex min-h-0 flex-col gap-4 xl:flex-row xl:items-stretch">
        {buckets.map((col) => (
          <LaundryPipelineColumn
            key={col.id}
            id={col.id}
            title={col.title}
            count={col.deals.length}
            deals={col.deals}
            loading={q.isLoading}
            accent={col.accent}
            emptyTitle={col.emptyTitle}
            selectable={selectMode}
            selectedIds={selectedIds}
            onToggleSelect={toggleSelected}
            className="w-full xl:min-w-[320px] xl:max-w-none"
          />
        ))}
      </div>
    </div>
  );
}
