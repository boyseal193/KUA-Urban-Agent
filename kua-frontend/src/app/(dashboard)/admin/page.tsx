"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Database,
  FlaskConical,
  Trash2,
  AlertOctagon,
  Loader2,
  RefreshCcw,
  Skull,
  Sparkles,
} from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { adminApi, propertiesApi } from "@/lib/api";
import type { DuplicateCluster } from "@/lib/api/properties";
import { ApiError } from "@/lib/api/client";
import { dealKeys } from "@/hooks/use-deals";
import { cn } from "@/lib/utils";

export default function AdminPage() {
  const qc = useQueryClient();

  const stats = useQuery({
    queryKey: ["admin-stats"],
    queryFn: () => adminApi.stats(),
    refetchInterval: 30_000,
  });

  const duplicates = useQuery({
    queryKey: ["admin-duplicates"],
    queryFn: () => propertiesApi.duplicates(100),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["admin-stats"] });
    qc.invalidateQueries({ queryKey: ["admin-duplicates"] });
    qc.invalidateQueries({ queryKey: dealKeys.all });
    qc.invalidateQueries({ queryKey: ["scan-history-full"] });
  };

  const purgeTest = useMutation({
    mutationFn: () => adminApi.purgeTestData(),
    onSuccess: (r) => {
      toast.success("Test data purged", { description: `${r.deleted ?? 0} properties soft-deleted.` });
      invalidate();
    },
    onError: (err) => toast.error("Purge failed", { description: errMsg(err) }),
  });

  const purgeFailed = useMutation({
    mutationFn: () => adminApi.purgeFailedJobs(1),
    onSuccess: (r) => {
      toast.success("Failed jobs purged", { description: `${r.deleted ?? 0} job records removed.` });
      invalidate();
    },
    onError: (err) => toast.error("Purge failed", { description: errMsg(err) }),
  });

  const purgeOrphans = useMutation({
    mutationFn: () => adminApi.purgeOrphans(),
    onSuccess: (r) => {
      const summary = Object.entries(r.deleted || {})
        .map(([k, v]) => `${v} ${k}`)
        .join(" · ");
      toast.success("Orphans purged", { description: summary || "Done." });
      invalidate();
    },
    onError: (err) => toast.error("Purge failed", { description: errMsg(err) }),
  });

  const statValues = stats.data?.stats ?? {};
  const clusters: DuplicateCluster[] = duplicates.data?.clusters ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="OPS · ADMIN"
        title="Admin & cleanup"
        subtitle="System statistics, duplicate inspection, and bulk cleanup tools."
        rightSlot={
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={invalidate}
            disabled={stats.isFetching}
            className="gap-1.5"
          >
            {stats.isFetching ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCcw className="h-3 w-3" />
            )}
            Refresh
          </Button>
        }
      />

      {/* Stats grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          icon={Database}
          label="Active properties"
          value={statValues.properties_active}
          tone="default"
        />
        <StatCard
          icon={Trash2}
          label="Deleted properties"
          value={statValues.properties_deleted}
          tone="muted"
        />
        <StatCard
          icon={FlaskConical}
          label="Test records"
          value={statValues.properties_test}
          tone="amber"
        />
        <StatCard
          icon={Sparkles}
          label="Active scans"
          value={statValues.scan_jobs_active}
          tone="primary"
        />
        <StatCard
          icon={AlertOctagon}
          label="Failed scans"
          value={statValues.scan_jobs_failed}
          tone="destructive"
        />
      </div>

      {/* Cleanup actions */}
      <div className="panel-strong p-5">
        <header className="mb-4 flex items-center gap-2">
          <Skull className="h-3.5 w-3.5 text-destructive" />
          <h3 className="text-sm font-semibold text-foreground">Cleanup actions</h3>
        </header>
        <p className="mb-4 text-xs text-muted-foreground">
          All cleanup actions are <span className="text-foreground">soft-delete</span> where possible
          (recoverable for 30 days via the audit log). Hard deletes are limited to failed scan jobs
          older than 24h.
        </p>
        <div className="grid gap-3 md:grid-cols-3">
          <ActionCard
            icon={FlaskConical}
            title="Purge test data"
            description="Soft-delete every property flagged is_test=TRUE."
            cta="Purge test"
            tone="amber"
            isPending={purgeTest.isPending}
            onClick={() => {
              if (!confirm("Soft-delete all test-flagged properties?")) return;
              purgeTest.mutate();
            }}
          />
          <ActionCard
            icon={AlertOctagon}
            title="Purge failed jobs"
            description="Hard-delete scan_jobs with status failed/timeout/cancelled older than 24h."
            cta="Purge failed"
            tone="destructive"
            isPending={purgeFailed.isPending}
            onClick={() => {
              if (!confirm("Hard-delete failed scan jobs older than 24h? This cannot be undone."))
                return;
              purgeFailed.mutate();
            }}
          />
          <ActionCard
            icon={Database}
            title="Purge orphans"
            description="Remove analyses/memos whose parent property no longer exists."
            cta="Purge orphans"
            tone="muted"
            isPending={purgeOrphans.isPending}
            onClick={() => purgeOrphans.mutate()}
          />
        </div>
      </div>

      {/* Duplicate clusters */}
      <div className="panel">
        <header className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">
              Duplicate clusters
            </h3>
            {duplicates.isFetching && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
          </div>
          <Badge variant="outline" className="font-mono text-[10px]">
            {clusters.length} cluster{clusters.length === 1 ? "" : "s"}
          </Badge>
        </header>
        {duplicates.isLoading ? (
          <div className="px-4 py-6 text-xs text-muted-foreground">
            <Loader2 className="inline h-3 w-3 animate-spin" /> Scanning…
          </div>
        ) : clusters.length === 0 ? (
          <div className="px-4 py-10 text-center text-xs text-muted-foreground">
            No active duplicates detected. The unique index on{" "}
            <code className="font-mono text-foreground">dedupe_key</code> is doing its job.
          </div>
        ) : (
          <ul className="divide-y divide-border/40">
            {clusters.map((cluster) => (
              <li key={cluster.dedupe_key} className="space-y-2 px-4 py-3">
                <div className="flex items-center justify-between">
                  <code className="rounded bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                    {cluster.dedupe_key}
                  </code>
                  <Badge variant="outline">{cluster.size} rows</Badge>
                </div>
                <ul className="space-y-1 pl-3 text-[11px]">
                  {cluster.properties.map((p) => (
                    <li key={p.id} className="flex flex-wrap items-center gap-2">
                      <code className="font-mono text-[10px] text-muted-foreground">
                        {String(p.id).slice(0, 8)}
                      </code>
                      <span className="truncate text-foreground">
                        {p.address ?? p.listing_url ?? "—"}
                      </span>
                      {typeof p.score === "number" && (
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {p.score}
                        </Badge>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | null | undefined;
  tone: "default" | "primary" | "amber" | "destructive" | "muted";
}) {
  const toneClass = {
    default: "text-foreground",
    primary: "text-primary",
    amber: "text-amber-300",
    destructive: "text-destructive",
    muted: "text-muted-foreground",
  }[tone];
  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 tactical-mono">
        <Icon className="h-3 w-3" /> {label}
      </div>
      <div className={cn("mt-2 font-display text-2xl font-semibold tabular-nums", toneClass)}>
        {value == null ? "—" : value.toLocaleString()}
      </div>
    </div>
  );
}

function ActionCard({
  icon: Icon,
  title,
  description,
  cta,
  tone,
  isPending,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  cta: string;
  tone: "amber" | "destructive" | "muted";
  isPending: boolean;
  onClick: () => void;
}) {
  const button = {
    amber: "bg-amber-500/90 hover:bg-amber-500 text-black",
    destructive: "bg-destructive/90 hover:bg-destructive text-destructive-foreground",
    muted: "bg-card hover:bg-card/80 text-foreground border border-border",
  }[tone];
  return (
    <div className="panel space-y-3 p-4">
      <div className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      </div>
      <p className="text-[11px] leading-snug text-muted-foreground">{description}</p>
      <Button
        type="button"
        size="sm"
        onClick={onClick}
        disabled={isPending}
        className={cn("w-full gap-2", button)}
      >
        {isPending ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Icon className="h-3.5 w-3.5" />
        )}
        {cta}
      </Button>
    </div>
  );
}

function errMsg(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Unknown error";
}
