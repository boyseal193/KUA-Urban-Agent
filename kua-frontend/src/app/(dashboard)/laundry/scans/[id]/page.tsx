"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, AlertCircle, AlertTriangle } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/common/empty-state";
import { LaundryScanListingCard } from "@/components/laundry/laundry-scan-listing-card";
import { useLaundryScan } from "@/hooks/use-laundry";
import type { LaundrySearchDiagnostics } from "@/lib/api";

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
  skipped: "#FACC15",
  retrying: "#38BDF8",
};

const STATUS_LABEL: Record<string, string> = {
  no_results: "NO RESULTS",
  success: "SUCCESS",
};

const LISTING_STEP_KEY = "laundry_process_listing";

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status.replace(/_/g, " ").toUpperCase();
}

export default function LaundryScanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const q = useLaundryScan(id);

  const job = q.data?.job;
  const steps = q.data?.steps ?? [];
  const properties = q.data?.properties ?? [];
  const listings = q.data?.listings ?? [];
  const summary = q.data?.summary;
  const searchDiagnostics = q.data?.search_diagnostics ?? null;

  const jobSteps = steps.filter((s) => (s.listing_index ?? -1) < 0);
  const listingSteps = steps.filter((s) => (s.listing_index ?? -1) >= 0);

  const isNoResults = job?.status === "no_results";
  const isFailed = job?.status === "failed";
  const showMismatchWarning = Boolean(
    summary?.summary_property_mismatch ||
      summary?.results_missing ||
      ((job?.listings_done ?? 0) > 0 && properties.length === 0),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · SCAN"
        title={job ? `Scan ${job.id.slice(0, 8)}` : "Scan"}
        subtitle={
          job
            ? `Status ${statusLabel(job.status)} · ${Math.round(job.progress_pct)}% · ${job.listings_done ?? 0}/${job.listings_total ?? 0} listings`
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

      {showMismatchWarning && (
        <Card>
          <CardContent className="flex gap-3 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-300" />
            <div className="space-y-1 text-xs">
              <p className="font-mono uppercase tracking-widest text-amber-200">
                Scan summary reports listings but result rows are missing
              </p>
              <p className="text-muted-foreground">
                Job counters show {job?.listings_done ?? 0}/{job?.listings_total ?? 0} processed, but{" "}
                {properties.length} property row(s) and {listings.length} listing result row(s) were returned.
                Check worker logs and Supabase persistence.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {(isNoResults || isFailed) && job?.error_message && (
        <Card>
          <CardContent className="flex gap-3 p-4">
            <AlertCircle
              className={`mt-0.5 h-4 w-4 flex-shrink-0 ${isFailed ? "text-rose-300" : "text-amber-300"}`}
            />
            <div className="space-y-1 text-xs">
              <p
                className={`font-mono uppercase tracking-widest ${isFailed ? "text-rose-200" : "text-amber-200"}`}
              >
                {isFailed ? "Scan failed" : "No listings found"}
              </p>
              <p className="text-muted-foreground">{job.error_message}</p>
              {job.search_url && (
                <p className="break-all font-mono text-[11px] text-muted-foreground">
                  Search URL: {job.search_url}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {searchDiagnostics && (
        <Card>
          <CardHeader>
            <CardTitle>Search diagnostics</CardTitle>
          </CardHeader>
          <CardContent>
            <SearchDiagnosticsDetail diagnostics={searchDiagnostics} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>
            Results · {properties.length} listing{properties.length === 1 ? "" : "s"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {q.isLoading ? (
            <div className="space-y-3">
              {[0, 1].map((i) => (
                <div key={i} className="h-40 animate-pulse rounded-md border border-border/60 bg-card/40" />
              ))}
            </div>
          ) : properties.length === 0 ? (
            <EmptyState
              title="No listing results"
              description={
                listings.length > 0
                  ? "Listing telemetry exists but no property rows were persisted for this scan."
                  : "This scan has not produced any scored properties yet."
              }
            />
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {properties.map((property, index) => (
                <LaundryScanListingCard key={property.id} property={property} index={index} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            <Row k="Status" v={statusLabel(job?.status ?? "—")} />
            <Row k="Search type" v={job?.search_type ?? "—"} />
            <Row k="Property type" v={job?.property_type ?? "—"} />
            <Row k="Acquisition" v={job?.acquisition_type ?? "—"} />
            <Row k="Search URL" v={job?.search_url ?? "—"} mono />
            <Row k="Limit" v={job?.listing_limit?.toString() ?? "—"} />
            <Row k="Approved" v={String(summary?.approved_count ?? job?.approved_count ?? 0)} />
            <Row k="Review" v={String(summary?.manual_review_count ?? job?.manual_review_count ?? 0)} />
            <Row k="Rejected" v={String(summary?.rejected_count ?? job?.rejected_count ?? 0)} />
            <Row k="Extraction failed" v={String(summary?.extraction_failed_count ?? 0)} />
            <Row k="Failed" v={String(summary?.listings_failed ?? job?.listings_failed ?? 0)} />
            <Row k="Persisted" v={String(summary?.persisted_count ?? properties.length)} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Worker pipeline</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[640px] overflow-y-auto">
              <table className="min-w-full text-xs">
                <thead className="sticky top-0 border-b border-border/60 bg-card/80 backdrop-blur text-left font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-2">#</th>
                    <th className="py-2 pr-2">Step</th>
                    <th className="py-2 pr-2">Status</th>
                    <th className="py-2 pr-2">URL / detail</th>
                  </tr>
                </thead>
                <tbody>
                  {jobSteps.map((s) => (
                    <tr key={s.id} className="border-b border-border/40">
                      <td className="py-2 pr-2 font-mono text-[10px]">{s.step_order}</td>
                      <td className="py-2 pr-2">{s.step_key.replace(/^laundry_/, "")}</td>
                      <td className="py-2 pr-2">
                        <StatusBadge status={s.status} />
                      </td>
                      <td className="max-w-[420px] truncate py-2 pr-2 font-mono text-[10px] text-muted-foreground">
                        {s.error_message ?? s.listing_url ?? "—"}
                      </td>
                    </tr>
                  ))}
                  {listingSteps.length > 0 && (
                    <tr>
                      <td
                        colSpan={4}
                        className="pb-1 pt-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground"
                      >
                        Per-listing
                      </td>
                    </tr>
                  )}
                  {listingSteps.map((s) => {
                    const label = s.step_key === LISTING_STEP_KEY ? "process listing" : s.step_key;
                    return (
                      <tr key={s.id} className="border-b border-border/40">
                        <td className="py-2 pr-2 font-mono text-[10px]">{(s.listing_index ?? 0) + 1}</td>
                        <td className="py-2 pr-2">{label}</td>
                        <td className="py-2 pr-2">
                          <StatusBadge status={s.status} />
                        </td>
                        <td className="max-w-[420px] truncate py-2 pr-2 font-mono text-[10px] text-muted-foreground">
                          {s.error_message ?? s.listing_url ?? "—"}
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

function StatusBadge({ status }: { status: string }) {
  const c = STATUS_COLOR[status] ?? "#94A3B8";
  return (
    <span
      className="rounded-md px-2 py-0.5 font-mono text-[10px] uppercase"
      style={{ color: c, background: `${c}1A`, border: `1px solid ${c}55` }}
    >
      {statusLabel(status)}
    </span>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{k}</span>
      <span
        className={
          mono
            ? "max-w-[260px] truncate font-mono text-[11px] text-foreground"
            : "text-foreground"
        }
        title={mono ? v : undefined}
      >
        {v}
      </span>
    </div>
  );
}

function SearchDiagnosticsDetail({ diagnostics }: { diagnostics: LaundrySearchDiagnostics }) {
  const applied = Object.entries(diagnostics.applied_filters ?? {});
  const removed = diagnostics.removed_filters ?? [];

  return (
    <div className="space-y-3 text-xs">
      {diagnostics.search_broadened && (
        <div className="rounded-md border border-amber-400/30 bg-amber-400/[0.06] p-3">
          <p className="font-mono uppercase tracking-widest text-amber-200">
            Search broadened automatically
          </p>
          <p className="mt-1 text-muted-foreground">
            Reason: {diagnostics.broadening_reason ?? "No listings found under original constraints"}
          </p>
        </div>
      )}
      <Row k="Generated URL" v={diagnostics.generated_url} mono />
      <Row
        k="Listing count"
        v={diagnostics.listing_count != null ? String(diagnostics.listing_count) : "—"}
      />
      <Row k="Fallback level" v={diagnostics.fallback_level.replace(/_/g, " ")} />
      <Row k="Stage" v={String(diagnostics.stage)} />
      {applied.length > 0 && (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Applied filters
          </p>
          <ul className="mt-1 list-disc pl-4 text-muted-foreground">
            {applied.map(([key, val]) => (
              <li key={key}>
                {key}: {val != null && val !== "" ? String(val) : "—"}
              </li>
            ))}
          </ul>
        </div>
      )}
      {removed.length > 0 && (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Removed filters
          </p>
          <p className="text-muted-foreground">{removed.join(", ")}</p>
        </div>
      )}
    </div>
  );
}
