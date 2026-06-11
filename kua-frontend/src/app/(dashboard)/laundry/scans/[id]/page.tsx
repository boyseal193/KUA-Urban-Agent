"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, AlertCircle, AlertTriangle, ExternalLink } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { LaundryPipelineExportMenu } from "@/components/laundry/laundry-export-actions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/common/empty-state";
import { LaundryScanListingCard } from "@/components/laundry/laundry-scan-listing-card";
import { useLaundryScan } from "@/hooks/use-laundry";
import { formatLaundryListingProgress } from "@/lib/api/laundry";
import type { LaundryScanListingResult, LaundrySearchDiagnostics } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  pending: "#94A3B8",
  queued: "#94A3B8",
  running: "#A78BFA",
  retrying: "#38BDF8",
  success: "#7CFAB3",
  duplicate: "#C4B5FD",
  filtered_out: "#FACC15",
  scrape_failed: "#FB7185",
  extraction_failed: "#FB923C",
  persistence_failed: "#F87171",
  scoring_failed: "#FB7185",
  memo_failed: "#FB7185",
  export_failed: "#FB7185",
  failed: "#FB7185",
  skipped: "#FACC15",
  completed: "#7CFAB3",
  no_results: "#FACC15",
  cancelled: "#FB7185",
  timeout: "#FB7185",
};

const STATUS_LABEL: Record<string, string> = {
  no_results: "NO RESULTS",
  success: "SUCCESS",
  duplicate: "DUPLICATE",
  filtered_out: "FILTERED OUT",
  scrape_failed: "SCRAPE FAILED",
  extraction_failed: "EXTRACTION FAILED",
  persistence_failed: "PERSISTENCE FAILED",
  scoring_failed: "SCORING FAILED",
  memo_failed: "MEMO FAILED",
  export_failed: "EXPORT FAILED",
  skipped: "FAILED",
};

const LISTING_STEP_KEY = "laundry_process_listing";

function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status.replace(/_/g, " ").toUpperCase();
}

function listingReason(row: LaundryScanListingResult): string {
  const result = (row.result ?? {}) as Record<string, unknown>;
  return (
    row.reason_message ??
    row.error_message ??
    (typeof result.reason_message === "string" ? result.reason_message : undefined) ??
    (typeof result.skip_reason === "string" ? result.skip_reason : undefined) ??
    "—"
  );
}

function listingStatus(row: LaundryScanListingResult): string {
  const raw = (row.status ?? "pending").toLowerCase();
  if (raw === "skipped") {
    const code = row.reason_code ?? (row.result as Record<string, unknown> | undefined)?.skip_reason;
    if (code === "duplicate_in_batch" || code === "known_listing_url" || code === "already_processed_in_job") {
      return "duplicate";
    }
    if (code === "listing_limit") return "filtered_out";
    return "failed";
  }
  return raw;
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

  const showAvailabilityNote = Boolean(summary?.availability_message);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · SCAN"
        title={job ? `Scan ${job.id.slice(0, 8)}` : "Scan"}
        subtitle={
          job
            ? `Status ${statusLabel(job.status)} · ${Math.round(job.progress_pct)}% · ${formatLaundryListingProgress(job, summary)} listings`
            : "Loading…"
        }
        rightSlot={
          <div className="flex flex-wrap items-center gap-3">
            <LaundryPipelineExportMenu scanId={id} />
            <Link
              href="/laundry/scans"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> History
            </Link>
          </div>
        }
      />

      {showAvailabilityNote && (
        <Card>
          <CardContent className="flex gap-3 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-300" />
            <div className="space-y-1 text-xs">
              <p className="font-mono uppercase tracking-widest text-amber-200">Source listing cap</p>
              <p className="text-muted-foreground">{summary?.availability_message}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {showMismatchWarning && (
        <Card>
          <CardContent className="flex gap-3 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-300" />
            <div className="space-y-1 text-xs">
              <p className="font-mono uppercase tracking-widest text-amber-200">
                Scan summary reports listings but result rows are missing
              </p>
              <p className="text-muted-foreground">
                Job counters show {formatLaundryListingProgress(job, summary)} processed, but {properties.length}{" "}
                property row(s) and {listings.length} listing result row(s) were returned.
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
              <p className={`font-mono uppercase tracking-widest ${isFailed ? "text-rose-200" : "text-amber-200"}`}>
                {isFailed ? "Scan failed" : "No listings found"}
              </p>
              <p className="text-muted-foreground">{job.error_message}</p>
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

      {summary && (
        <Card>
          <CardHeader>
            <CardTitle>Listing accounting</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <DiagStat label="Discovered" value={summary.discovered_count ?? summary.listings_found ?? 0} />
            <DiagStat label="Queued" value={summary.queued_count ?? summary.listings_queued ?? 0} />
            <DiagStat label="Processed" value={summary.processed_count ?? summary.listings_processed ?? 0} />
            <DiagStat label="Successful" value={summary.success_count ?? 0} />
            <DiagStat label="Duplicates" value={summary.duplicate_count ?? 0} />
            <DiagStat label="Filtered out" value={summary.filtered_out_count ?? 0} />
            <DiagStat label="Failed" value={summary.failed_count ?? summary.listings_failed_count ?? 0} />
            <DiagStat label="Pending" value={Math.max(0, (summary.discovered_count ?? 0) - listings.length)} />
            <DiagStat label="Retried" value={summary.listings_retried ?? 0} />
          </CardContent>
          {summary.invariant_ok === false && (
            <CardContent className="border-t border-border/60 pt-3 text-xs text-amber-200">
              Listing count mismatch (delta {summary.invariant_delta ?? "?"}). Every discovered URL must reach a
              terminal status.
            </CardContent>
          )}
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Listing ledger · {listings.length} URL{listings.length === 1 ? "" : "s"}</CardTitle>
        </CardHeader>
        <CardContent>
          {listings.length === 0 ? (
            <EmptyState title="No listing rows yet" description="Results appear here as the worker processes each URL." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="border-b border-border/60 text-left font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-2">#</th>
                    <th className="py-2 pr-2">Status</th>
                    <th className="py-2 pr-2">Reason</th>
                    <th className="py-2 pr-2">Attempts</th>
                    <th className="py-2 pr-2">Stage</th>
                    <th className="py-2 pr-2">URL</th>
                    <th className="py-2 pr-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {listings.map((row) => {
                    const st = listingStatus(row);
                    const result = (row.result ?? {}) as Record<string, unknown>;
                    return (
                      <tr key={`${row.listing_index}-${row.listing_url}`} className="border-b border-border/40">
                        <td className="py-2 pr-2 font-mono tabular-nums">{(row.listing_index ?? 0) + 1}</td>
                        <td className="py-2 pr-2">
                          <StatusBadge status={st} />
                        </td>
                        <td className="max-w-[280px] py-2 pr-2 text-muted-foreground">{listingReason(row)}</td>
                        <td className="py-2 pr-2 font-mono tabular-nums">
                          {row.attempt_count ?? (typeof result.attempt_count === "number" ? result.attempt_count : "—")}
                        </td>
                        <td className="py-2 pr-2 font-mono text-[10px] text-muted-foreground">
                          {row.stage_failed ?? (typeof result.stage_failed === "string" ? result.stage_failed : "—")}
                        </td>
                        <td className="max-w-[220px] truncate py-2 pr-2 font-mono text-[10px]">{row.listing_url ?? "—"}</td>
                        <td className="py-2 pr-2">
                          {row.listing_url ? (
                            <a
                              href={row.listing_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-violet-300 hover:underline"
                            >
                              Open <ExternalLink className="h-3 w-3" />
                            </a>
                          ) : null}
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

      <Card>
        <CardHeader>
          <CardTitle>
            Scored properties · {properties.length} listing{properties.length === 1 ? "" : "s"}
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
              title="No scored properties"
              description="Failed, duplicate, or filtered listings may still appear in the listing ledger above."
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
            <Row k="Requested" v={String(summary?.requested_limit ?? job?.listing_limit ?? "—")} />
            <Row k="Discovered" v={String(summary?.discovered_count ?? "—")} />
            <Row k="Successful" v={String(summary?.success_count ?? 0)} />
            <Row k="Duplicates" v={String(summary?.duplicate_count ?? 0)} />
            <Row k="Filtered out" v={String(summary?.filtered_out_count ?? 0)} />
            <Row k="Failed" v={String(summary?.failed_count ?? 0)} />
            <Row k="Approved" v={String(summary?.approved_count ?? job?.approved_count ?? 0)} />
            <Row k="Review" v={String(summary?.manual_review_count ?? job?.manual_review_count ?? 0)} />
            <Row k="Rejected" v={String(summary?.rejected_count ?? job?.rejected_count ?? 0)} />
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
                    <th className="py-2 pr-2">Reason / URL</th>
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
                      <td colSpan={4} className="pb-1 pt-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        Per-listing
                      </td>
                    </tr>
                  )}
                  {listingSteps.map((s) => {
                    const out = (s.output_data ?? s.result ?? {}) as Record<string, unknown>;
                    const displayStatus =
                      typeof out.terminal_status === "string" ? out.terminal_status : s.status;
                    const reason =
                      s.error_message ??
                      (typeof out.reason_message === "string" ? out.reason_message : undefined) ??
                      s.listing_url ??
                      "—";
                    return (
                      <tr key={s.id} className="border-b border-border/40">
                        <td className="py-2 pr-2 font-mono text-[10px]">{(s.listing_index ?? 0) + 1}</td>
                        <td className="py-2 pr-2">process listing</td>
                        <td className="py-2 pr-2">
                          <StatusBadge status={displayStatus} />
                        </td>
                        <td className="max-w-[420px] truncate py-2 pr-2 font-mono text-[10px] text-muted-foreground">
                          {reason}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
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

function DiagStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md border border-border/60 bg-card/40 px-3 py-2">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">{value}</p>
    </div>
  );
}

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{k}</span>
      <span
        className={mono ? "max-w-[260px] truncate font-mono text-[11px] text-foreground" : "text-foreground"}
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
          <p className="font-mono uppercase tracking-widest text-amber-200">Search broadened automatically</p>
          <p className="mt-1 text-muted-foreground">
            Reason: {diagnostics.broadening_reason ?? "No listings found under original constraints"}
          </p>
        </div>
      )}
      <Row k="Generated URL" v={diagnostics.generated_url} mono />
      <Row k="Listing count" v={diagnostics.listing_count != null ? String(diagnostics.listing_count) : "—"} />
      <Row k="Fallback level" v={diagnostics.fallback_level.replace(/_/g, " ")} />
      <Row k="Stage" v={String(diagnostics.stage)} />
      {applied.length > 0 && (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Applied filters</p>
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
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Removed filters</p>
          <p className="text-muted-foreground">{removed.join(", ")}</p>
        </div>
      )}
    </div>
  );
}
