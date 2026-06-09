"use client";

import Link from "next/link";
import { Activity, RotateCcw } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/empty-state";
import { useLaundryScans } from "@/hooks/use-laundry";
import { laundryApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";

const STATUS_COLOR: Record<string, string> = {
  pending: "#94A3B8",
  queued: "#94A3B8",
  running: "#A78BFA",
  success: "#7CFAB3",
  completed: "#7CFAB3",
  no_results: "#FACC15",
  failed: "#FB7185",
  cancelled: "#FB7185",
  timeout: "#FB7185",
};

const STATUS_LABEL: Record<string, string> = {
  no_results: "NO RESULTS",
};

const RESUMABLE = new Set(["failed", "cancelled", "timeout", "no_results"]);

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status.replace(/_/g, " ").toUpperCase();
}

export default function LaundryScansPage() {
  const scans = useLaundryScans(50);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · SCAN HISTORY"
        title="Background Scans"
        subtitle="Every queued or completed laundry scan, with progress, results and resume controls."
        rightSlot={
          <Link href="/laundry/scan">
            <Button variant="tactical" size="sm" className="bg-violet-500/10 text-violet-300 hover:bg-violet-500/20">
              New scan
            </Button>
          </Link>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>History</CardTitle>
        </CardHeader>
        <CardContent>
          {scans.isLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-14 animate-pulse rounded-md border border-border/60 bg-card/40" />
              ))}
            </div>
          ) : (scans.data ?? []).length === 0 ? (
            <EmptyState
              title="No scans yet"
              description="Launch a scan to see live progress and historic runs."
              icon={Activity}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="border-b border-border/60 text-left font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-2">ID</th>
                    <th className="py-2 pr-2">Type</th>
                    <th className="py-2 pr-2">Status</th>
                    <th className="py-2 pr-2">Listings</th>
                    <th className="py-2 pr-2">Approved · Review · Reject</th>
                    <th className="py-2 pr-2">Progress</th>
                    <th className="py-2 pr-2">Created</th>
                    <th className="py-2 pr-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {(scans.data ?? []).map((s) => {
                    const color = STATUS_COLOR[s.status] ?? "#94A3B8";
                    return (
                      <tr key={s.id} className="border-b border-border/40 hover:bg-white/[0.02]">
                        <td className="py-2 pr-2 font-mono text-[10px] text-muted-foreground">
                          <Link className="text-violet-300 hover:underline" href={`/laundry/scans/${s.id}`}>
                            {s.id.slice(0, 8)}
                          </Link>
                        </td>
                        <td className="py-2 pr-2 uppercase tracking-widest text-[10px] text-muted-foreground">
                          {(s.search_type ?? "").replace(/_/g, " ")}
                        </td>
                        <td className="py-2 pr-2">
                          <span
                            className="rounded-md px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
                            style={{
                              color,
                              backgroundColor: `${color}1A`,
                              border: `1px solid ${color}55`,
                            }}
                          >
                            {statusLabel(s.status)}
                          </span>
                        </td>
                        <td className="py-2 pr-2 font-mono tabular-nums">
                          {s.listings_done}/{s.listings_total}
                          {s.listings_failed ? ` (${s.listings_failed} failed)` : ""}
                        </td>
                        <td className="py-2 pr-2 font-mono tabular-nums">
                          {s.approved_count} · {s.manual_review_count} · {s.rejected_count}
                        </td>
                        <td className="py-2 pr-2 font-mono tabular-nums">
                          {Math.round(s.progress_pct)}%
                        </td>
                        <td className="py-2 pr-2 text-muted-foreground">{timeAgo(s.created_at)}</td>
                        <td className="py-2 pr-2">
                          {RESUMABLE.has(s.status) && (
                            <button
                              className="inline-flex items-center gap-1 rounded border border-border/60 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest hover:border-violet-400/50 hover:text-violet-300"
                              onClick={async () => {
                                await laundryApi.resumeScan(s.id);
                                scans.refetch();
                              }}
                            >
                              <RotateCcw className="h-3 w-3" /> Resume
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
