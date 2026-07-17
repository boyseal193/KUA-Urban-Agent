"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { History, Loader2, RefreshCcw, ArrowUpRight, Filter } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ExportButtons } from "@/components/scan/export-buttons";
import { jobsApi } from "@/lib/api";
import { describeApiError } from "@/lib/api/client";
import type { ScanJobRecord } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "success", label: "Success" },
  { value: "failed", label: "Failed" },
  { value: "running", label: "Running" },
  { value: "queued", label: "Queued" },
  { value: "cancelled", label: "Cancelled" },
] as const;

const STATUS_META: Record<string, { label: string; className: string }> = {
  success:   { label: "Success",   className: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" },
  failed:    { label: "Failed",    className: "border-destructive/40 bg-destructive/10 text-destructive" },
  cancelled: { label: "Cancelled", className: "border-muted/40 bg-muted/10 text-muted-foreground" },
  timeout:   { label: "Timeout",   className: "border-amber-500/40 bg-amber-500/10 text-amber-300" },
  running:   { label: "Running",   className: "border-primary/40 bg-primary/10 text-primary" },
  retrying:  { label: "Retrying",  className: "border-primary/40 bg-primary/10 text-primary" },
  queued:    { label: "Queued",    className: "border-border bg-card text-muted-foreground" },
  pending:   { label: "Pending",   className: "border-border bg-card text-muted-foreground" },
};

function fmtTs(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function durationMs(a?: string | null, b?: string | null): string {
  if (!a || !b) return "—";
  try {
    const ms = new Date(b).getTime() - new Date(a).getTime();
    if (ms < 1000) return `${ms} ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
  } catch {
    return "—";
  }
}

export default function ScansPage() {
  const qc = useQueryClient();
  const [status, setStatus] = React.useState<string>("");
  const [limit, setLimit] = React.useState<number>(50);

  const query = useQuery({
    queryKey: ["scan-history-full", status, limit],
    queryFn: () => jobsApi.listJobs(limit, status || undefined),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
  });

  const jobs: ScanJobRecord[] = React.useMemo(() => {
    const list = query.data?.jobs;
    if (!Array.isArray(list)) return [];
    return list as ScanJobRecord[];
  }, [query.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="OPS · PIPELINE HISTORY"
        title="Scan history"
        subtitle="Every scan, every status. Re-download exports, replay timelines."
        rightSlot={
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              qc.invalidateQueries({ queryKey: ["scan-history-full"] });
            }}
            disabled={query.isFetching}
            className="gap-1.5"
          >
            {query.isFetching ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCcw className="h-3 w-3" />
            )}
            Refresh
          </Button>
        }
      />

      {/* Filter chips */}
      <div className="panel flex flex-wrap items-center gap-2 p-3">
        <Filter className="ml-2 h-3 w-3 text-muted-foreground" />
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          Status
        </span>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => setStatus(f.value)}
            className={cn(
              "rounded-md border px-2.5 py-1 text-[11px] font-mono uppercase tracking-widest transition",
              status === f.value
                ? "border-primary/60 bg-primary/[0.08] text-primary"
                : "border-border/60 bg-card/30 text-muted-foreground hover:border-primary/30 hover:text-foreground"
            )}
          >
            {f.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Limit
          </span>
          {[25, 50, 100, 200].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setLimit(n)}
              className={cn(
                "rounded-md border px-2 py-1 text-[10px] font-mono",
                limit === n
                  ? "border-primary/60 bg-primary/[0.08] text-primary"
                  : "border-border/60 bg-card/30 text-muted-foreground hover:border-primary/30"
              )}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="panel overflow-hidden">
        <header className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <History className="h-3.5 w-3.5 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">
              {jobs.length} scan{jobs.length === 1 ? "" : "s"}
            </h3>
          </div>
        </header>

        {query.isLoading ? (
          <div className="flex items-center gap-2 px-4 py-6 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Loading scans…
          </div>
        ) : query.isError ? (
          <div className="m-4 rounded-md border border-destructive/30 bg-destructive/[0.06] px-3 py-2 text-xs text-destructive">
            Failed to load scans: {describeApiError(query.error, "scan history request")}
          </div>
        ) : jobs.length === 0 ? (
          <div className="px-4 py-10 text-center text-xs text-muted-foreground">
            No scans match this filter.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-border/60 text-left font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2">Job</th>
                  <th className="px-4 py-2">Started</th>
                  <th className="px-4 py-2">Duration</th>
                  <th className="px-4 py-2">Listings</th>
                  <th className="px-4 py-2">Approved</th>
                  <th className="px-4 py-2 text-right">Exports</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const st = (job.status || "").toLowerCase();
                  const meta =
                    STATUS_META[st] ?? {
                      label: st || "unknown",
                      className: "border-border bg-card text-muted-foreground",
                    };
                  return (
                    <tr
                      key={job.id}
                      className="border-b border-border/40 transition hover:bg-white/[0.02]"
                    >
                      <td className="px-4 py-3">
                        <Badge
                          variant="outline"
                          className={cn(
                            "h-5 px-1.5 text-[9px] font-mono uppercase tracking-widest",
                            meta.className
                          )}
                        >
                          {meta.label}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <code className="rounded bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-foreground">
                            {job.id?.slice(0, 8)}
                          </code>
                          <span className="text-[11px] text-muted-foreground">
                            {(job.job_type || "—").replace(/_/g, " ")}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">
                        {fmtTs(job.created_at)}
                      </td>
                      <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">
                        {durationMs(job.started_at, job.finished_at)}
                      </td>
                      <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">
                        {job.listings_done ?? 0}/{job.listings_total ?? 0}
                      </td>
                      <td className="px-4 py-3 font-mono text-[11px] text-accent">
                        {job.approved_count ?? 0}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {st === "success" && job.id ? (
                          <ExportButtons
                            jobId={job.id}
                            variant="compact"
                            showRegenerate={false}
                          />
                        ) : (
                          <Link
                            href="/scan"
                            className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-primary"
                          >
                            Open <ArrowUpRight className="h-3 w-3" />
                          </Link>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
