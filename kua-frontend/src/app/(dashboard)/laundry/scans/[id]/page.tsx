"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLaundryScan } from "@/hooks/use-laundry";

const STATUS_COLOR: Record<string, string> = {
  pending: "#94A3B8",
  running: "#A78BFA",
  success: "#7CFAB3",
  completed: "#7CFAB3",
  failed: "#FB7185",
  skipped: "#FACC15",
  retrying: "#38BDF8",
};

export default function LaundryScanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const q = useLaundryScan(id);

  const job = q.data?.job;
  const steps = q.data?.steps ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · SCAN"
        title={job ? `Scan ${job.id.slice(0, 8)}` : "Scan"}
        subtitle={
          job
            ? `Status ${job.status.toUpperCase()} · ${Math.round(job.progress_pct)}% · ${job.listings_done}/${job.listings_total} listings`
            : "Loading…"
        }
        rightSlot={
          <Link
            href="/laundry/scans"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> History
          </Link>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            <Row k="Search type" v={job?.search_type ?? "—"} />
            <Row k="Property type" v={job?.property_type ?? "—"} />
            <Row k="Acquisition" v={job?.acquisition_type ?? "—"} />
            <Row k="Search URL" v={job?.search_url ?? "—"} mono />
            <Row k="Limit" v={job?.listing_limit?.toString() ?? "—"} />
            <Row k="Approved" v={String(job?.approved_count ?? 0)} />
            <Row k="Review" v={String(job?.manual_review_count ?? 0)} />
            <Row k="Rejected" v={String(job?.rejected_count ?? 0)} />
            <Row k="Failed" v={String(job?.listings_failed ?? 0)} />
            {job?.error_message && (
              <div className="rounded-md border border-rose-400/40 bg-rose-400/10 p-2 font-mono text-[10px] text-rose-200">
                {job.error_message}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Steps</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[640px] overflow-y-auto">
              <table className="min-w-full text-xs">
                <thead className="sticky top-0 border-b border-border/60 bg-card/80 backdrop-blur text-left font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-2">#</th>
                    <th className="py-2 pr-2">Step</th>
                    <th className="py-2 pr-2">Status</th>
                    <th className="py-2 pr-2">URL</th>
                  </tr>
                </thead>
                <tbody>
                  {steps.map((s) => {
                    const c = STATUS_COLOR[s.status] ?? "#94A3B8";
                    return (
                      <tr key={s.id} className="border-b border-border/40">
                        <td className="py-2 pr-2 font-mono text-[10px]">{s.step_order}</td>
                        <td className="py-2 pr-2">{s.step_key}</td>
                        <td className="py-2 pr-2">
                          <span
                            className="rounded-md px-2 py-0.5 font-mono text-[10px] uppercase"
                            style={{ color: c, background: `${c}1A`, border: `1px solid ${c}55` }}
                          >
                            {s.status}
                          </span>
                        </td>
                        <td className="py-2 pr-2 truncate max-w-[420px] font-mono text-[10px] text-muted-foreground">
                          {s.listing_url ?? "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {steps.length === 0 && (
                <div className="px-4 py-6 text-center text-xs text-muted-foreground">
                  Waiting for first step…
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {k}
      </span>
      <span
        className={mono ? "max-w-[260px] truncate font-mono text-[11px] text-foreground" : "text-foreground"}
        title={mono ? v : undefined}
      >
        {v}
      </span>
    </div>
  );
}
