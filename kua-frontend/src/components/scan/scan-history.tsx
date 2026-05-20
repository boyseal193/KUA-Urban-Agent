"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { History, Loader2, RefreshCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { jobsApi } from "@/lib/api";
import type { ScanJobRecord } from "@/lib/api/types";
import { ExportButtons } from "./export-buttons";

const STATUS_BADGE: Record<
  string,
  { label: string; className: string }
> = {
  success: { label: "Success", className: "border-accent/40 bg-accent/10 text-accent" },
  failed: {
    label: "Failed",
    className: "border-destructive/40 bg-destructive/10 text-destructive",
  },
  cancelled: {
    label: "Cancelled",
    className: "border-kua-amber/40 bg-kua-amber/10 text-kua-amber",
  },
  timeout: {
    label: "Timeout",
    className: "border-kua-amber/40 bg-kua-amber/10 text-kua-amber",
  },
  running: {
    label: "Running",
    className: "border-primary/40 bg-primary/10 text-primary",
  },
  retrying: {
    label: "Retrying",
    className: "border-primary/40 bg-primary/10 text-primary",
  },
  queued: {
    label: "Queued",
    className: "border-border bg-card text-muted-foreground",
  },
  pending: {
    label: "Pending",
    className: "border-border bg-card text-muted-foreground",
  },
};

function fmtTs(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

const TERMINAL_STATUSES = new Set(["success", "failed", "cancelled", "timeout"]);

export function ScanHistory({ limit = 8 }: { limit?: number }) {
  const query = useQuery({
    queryKey: ["scan-history", limit],
    queryFn: () => jobsApi.listJobs(limit),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  });

  const jobs: ScanJobRecord[] = React.useMemo(() => {
    const list = query.data?.jobs;
    if (!Array.isArray(list)) return [];
    return list as ScanJobRecord[];
  }, [query.data]);

  return (
    <div className="panel p-5">
      <header className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <History className="h-3.5 w-3.5 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            Recent scans
          </h3>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => query.refetch()}
          disabled={query.isFetching}
          className="gap-1.5"
        >
          {query.isFetching ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCcw className="h-3 w-3" />
          )}
          <span className="text-[10px] font-mono uppercase tracking-widest">
            Refresh
          </span>
        </Button>
      </header>

      {query.isLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          Loading scan history…
        </div>
      ) : query.isError ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/[0.06] px-3 py-2 text-xs text-destructive">
          Could not load scan history: {(query.error as Error)?.message}
        </div>
      ) : jobs.length === 0 ? (
        <div className="rounded-md border border-border/60 bg-card/30 px-3 py-6 text-center text-xs text-muted-foreground">
          No scans run yet. Launch one above — it will appear here.
        </div>
      ) : (
        <ul className="space-y-2">
          {jobs.map((job) => {
            const status = (job.status || "").toLowerCase();
            const meta =
              STATUS_BADGE[status] ?? {
                label: status || "unknown",
                className: "border-border bg-card text-muted-foreground",
              };
            const terminal = TERMINAL_STATUSES.has(status);
            const exportEligible = status === "success";
            return (
              <li
                key={job.id}
                className={cn(
                  "rounded-md border border-border/60 bg-card/30 px-3 py-2.5",
                  "transition-colors hover:border-primary/40"
                )}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          "h-5 px-1.5 text-[9px] font-mono uppercase tracking-widest",
                          meta.className
                        )}
                      >
                        {meta.label}
                      </Badge>
                      <span className="truncate text-[11px] font-mono text-muted-foreground">
                        {job.id?.slice(0, 12) ?? "—"}
                      </span>
                      {!terminal && (
                        <Loader2 className="h-3 w-3 animate-spin text-primary" />
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground">
                      <span>{fmtTs(job.created_at)}</span>
                      <span>
                        {job.listings_done ?? 0}/{job.listings_total ?? "—"} listings
                      </span>
                      {typeof job.approved_count === "number" && (
                        <span className="text-accent">
                          {job.approved_count} approved
                        </span>
                      )}
                      {typeof job.rejected_count === "number" && (
                        <span>{job.rejected_count} rejected</span>
                      )}
                    </div>
                  </div>
                  {exportEligible && job.id && (
                    <ExportButtons
                      jobId={job.id}
                      variant="compact"
                      showRegenerate={false}
                    />
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
