"use client";

import { useMemo, useState } from "react";
import { Columns3 } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import {
  LaundryBulkExportToolbar,
  LaundryPipelineExportMenu,
} from "@/components/laundry/laundry-export-actions";
import { LaundryDealList } from "@/components/laundry/laundry-deal-list";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useLaundryApprovedDeals,
  useLaundryManualReview,
  useLaundryRejected,
} from "@/hooks/use-laundry";

export default function LaundryPipelinePage() {
  const approved = useLaundryApprovedDeals(50);
  const review = useLaundryManualReview(50);
  const rejected = useLaundryRejected(50);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const failed = useMemo(
    () =>
      (rejected.data ?? []).filter(
        (d) => d.deal_status === "extraction_failed" || ((d.score ?? 0) < 40 && d.deal_status === "rejected"),
      ),
    [rejected.data],
  );

  function toggleSelected(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · PIPELINE"
        title="Acquisition Pipeline"
        subtitle="Laundry-specific deal pipeline — approved, manual review, rejected and low-score failures."
        rightSlot={<LaundryPipelineExportMenu />}
      />

      <Card>
        <CardHeader>
          <CardTitle>Bulk actions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="border border-border/60"
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
          <LaundryBulkExportToolbar selectedIds={selectedIds} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>
              <Columns3 className="mr-2 inline h-3.5 w-3.5 text-violet-300" />
              Approved
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LaundryDealList
              deals={(approved.data ?? []).slice(0, 25)}
              loading={approved.isLoading}
              emptyTitle="No approved deals"
              selectable={selectMode}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelected}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <Columns3 className="mr-2 inline h-3.5 w-3.5 text-sky-300" />
              Manual Review
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LaundryDealList
              deals={(review.data ?? []).slice(0, 25)}
              loading={review.isLoading}
              emptyTitle="Manual review queue is empty"
              selectable={selectMode}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelected}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <Columns3 className="mr-2 inline h-3.5 w-3.5 text-rose-300" />
              Rejected
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LaundryDealList
              deals={(rejected.data ?? []).slice(0, 25)}
              loading={rejected.isLoading}
              emptyTitle="Nothing rejected yet"
              selectable={selectMode}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelected}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <Columns3 className="mr-2 inline h-3.5 w-3.5 text-amber-300" />
              Failed / Low score
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LaundryDealList
              deals={failed.slice(0, 25)}
              loading={rejected.isLoading}
              emptyTitle="No failed deals"
              selectable={selectMode}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelected}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
