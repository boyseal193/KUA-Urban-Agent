"use client";

import * as React from "react";
import { Download, FileSpreadsheet, Inbox, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { laundryApi, type LaundryPipelineExportScope, type LaundryProperty } from "@/lib/api";
import { useCreateLaundryPipelineExport } from "@/hooks/use-laundry";
import { LaundryPipelineCard } from "./laundry-pipeline-card";

const SCOPE_BY_COLUMN: Record<string, LaundryPipelineExportScope> = {
  approved: "approved",
  review: "manual_review",
  rejected: "rejected",
  failed: "failed",
};

interface Props {
  id: string;
  title: string;
  count: number;
  deals: LaundryProperty[];
  loading?: boolean;
  accent: string;
  emptyTitle: string;
  selectable?: boolean;
  selectedIds?: string[];
  onToggleSelect?: (id: string) => void;
  className?: string;
}

export function LaundryPipelineColumn({
  id,
  title,
  count,
  deals,
  loading = false,
  accent,
  emptyTitle,
  selectable = false,
  selectedIds = [],
  onToggleSelect,
  className,
}: Props) {
  const exportColumn = useCreateLaundryPipelineExport();
  const [lastExportId, setLastExportId] = React.useState<string | null>(null);
  const scope = SCOPE_BY_COLUMN[id] ?? "entire";

  async function exportColumnDeals() {
    const toastId = toast.loading(`Exporting ${title}…`);
    try {
      const res = await exportColumn.mutateAsync(scope);
      setLastExportId(res.export_id);
      window.open(
        res.download_url
          ? `/api/proxy${res.download_url}`
          : laundryApi.downloadExportUrl(res.export_id),
        "_blank",
      );
      toast.success(`${title} export ready`, { id: toastId });
    } catch (err) {
      toast.error((err as Error).message, { id: toastId });
    }
  }

  return (
    <section
      className={cn(
        "flex min-h-[640px] min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border/70 bg-card/30 xl:min-h-[calc(100vh-14rem)]",
        className,
      )}
    >
      <div className="h-1 shrink-0" style={{ backgroundColor: accent }} />
      <header className="flex shrink-0 flex-col gap-3 border-b border-border/60 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-sm font-semibold uppercase tracking-[0.12em] text-foreground">
              {title}
            </h2>
            <p className="mt-0.5 font-mono text-xs tabular-nums text-muted-foreground">
              {count} {count === 1 ? "deal" : "deals"}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 border border-border/60 bg-background/30 font-mono text-[10px] uppercase tracking-widest"
              disabled={exportColumn.isPending || count === 0}
              onClick={exportColumnDeals}
            >
              {exportColumn.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <FileSpreadsheet className="h-3.5 w-3.5" />
              )}
              Export column
            </Button>
            {lastExportId && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 border border-border/60"
                onClick={() => window.open(laundryApi.downloadExportUrl(lastExportId), "_blank")}
              >
                <Download className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {loading ? (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-[420px] animate-pulse rounded-xl border border-border/60 bg-card/40"
              />
            ))}
          </div>
        ) : deals.length === 0 ? (
          <EmptyState icon={Inbox} title={emptyTitle} description="No opportunities in this stage." />
        ) : (
          <div className="flex w-full flex-col gap-4">
            {deals.map((deal) => (
              <LaundryPipelineCard
                key={deal.id}
                deal={deal}
                selectable={selectable}
                selected={selectedIds.includes(deal.id)}
                onToggleSelect={onToggleSelect}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
