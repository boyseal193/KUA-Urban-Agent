"use client";

import * as React from "react";
import Link from "next/link";
import {
  ExternalLink,
  FileSpreadsheet,
  FileText,
  Loader2,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { laundryApi, type LaundryProperty } from "@/lib/api";
import {
  aiSummary,
  districtLabel,
  pipelineMetrics,
  propertyTitle,
} from "@/lib/laundry-pipeline-utils";
import {
  useCreateLaundryExport,
  useDeleteLaundryProperty,
} from "@/hooks/use-laundry";
import { LaundryScoreBadge } from "./laundry-score-badge";
import { LaundryStatusBadge } from "./laundry-status";

interface Props {
  deal: LaundryProperty;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (id: string) => void;
  className?: string;
}

export function LaundryPipelineCard({
  deal,
  selectable = false,
  selected = false,
  onToggleSelect,
  className,
}: Props) {
  const createExport = useCreateLaundryExport(deal.id);
  const del = useDeleteLaundryProperty();
  const metrics = pipelineMetrics(deal);
  const summary = aiSummary(deal);

  async function exportDeal() {
    const toastId = toast.loading("Building deal workbook…");
    try {
      const res = await createExport.mutateAsync("excel");
      window.open(
        res.download_url
          ? `/api/proxy${res.download_url}`
          : laundryApi.downloadExportUrl(res.export_id),
        "_blank",
      );
      toast.success("Deal export ready", { id: toastId });
    } catch (err) {
      toast.error((err as Error).message, { id: toastId });
    }
  }

  async function deleteDeal() {
    if (!confirm("Remove this deal from the pipeline? (Soft delete — restorable.)")) return;
    try {
      await del.mutateAsync({ id: deal.id });
      toast.success("Deal removed");
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <article
      className={cn(
        "w-full rounded-xl border border-border/70 bg-card/50 shadow-sm transition-colors hover:border-violet-400/35 hover:bg-card/70",
        selected && "border-emerald-400/50 ring-1 ring-emerald-400/25",
        className,
      )}
    >
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex items-start gap-3">
          {selectable && (
            <button
              type="button"
              aria-pressed={selected}
              aria-label={selected ? "Deselect deal" : "Select deal"}
              className="mt-1 rounded border border-border/60 bg-background/60 p-1.5"
              onClick={() => onToggleSelect?.(deal.id)}
            >
              <span
                className={cn(
                  "block h-4 w-4 rounded-sm border",
                  selected ? "border-emerald-300 bg-emerald-400" : "border-muted-foreground/40",
                )}
              />
            </button>
          )}

          <LaundryScoreBadge score={deal.score ?? null} size="lg" className="shrink-0" />

          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md border border-violet-400/30 bg-violet-400/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-violet-200">
                {deal.verdict || "Pending verdict"}
              </span>
              <LaundryStatusBadge status={deal.deal_status} />
              {deal.classification && (
                <span className="rounded-md border border-border/60 bg-background/40 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  {deal.classification}
                </span>
              )}
            </div>

            <h3 className="break-words font-display text-base font-semibold leading-snug text-foreground">
              {propertyTitle(deal)}
            </h3>

            <dl className="grid gap-1 text-sm text-muted-foreground">
              <div className="flex flex-wrap gap-x-4 gap-y-0.5">
                <div>
                  <dt className="sr-only">Neighbourhood</dt>
                  <dd>{deal.neighbourhood || "—"}</dd>
                </div>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-0.5">
                <div>
                  <dt className="font-mono text-[10px] uppercase tracking-widest">District</dt>
                  <dd className="text-foreground">{districtLabel(deal)}</dd>
                </div>
                <div>
                  <dt className="font-mono text-[10px] uppercase tracking-widest">City</dt>
                  <dd className="text-foreground">{deal.city || "—"}</dd>
                </div>
              </div>
            </dl>
          </div>
        </div>
      </div>

      <Section title="Key metrics">
        <MetricGrid
          items={[
            { label: "Area", value: metrics.area },
            { label: "Machines", value: metrics.machines },
            { label: "Revenue", value: metrics.revenue },
            { label: "EBITDA", value: metrics.ebitda },
            { label: "Margin", value: metrics.margin },
            { label: "Payback", value: metrics.payback },
          ]}
        />
      </Section>

      <Section title="Financial summary">
        <MetricGrid
          items={[
            { label: "Monthly revenue", value: metrics.monthlyRevenue },
            { label: "Monthly profit", value: metrics.monthlyProfit },
            { label: "Annual EBITDA", value: metrics.annualEbitda },
            { label: "Investment req.", value: metrics.investment },
            { label: "ROI", value: metrics.roi },
            { label: "Payback years", value: metrics.paybackYears },
          ]}
        />
      </Section>

      <Section title="Opportunity summary">
        <MetricGrid
          items={[
            { label: "Locker revenue", value: metrics.locker },
            { label: "Vending revenue", value: metrics.vending },
            { label: "Upside potential", value: metrics.upside },
            { label: "Demand score", value: metrics.demand },
            { label: "Competition score", value: metrics.competition },
          ]}
          columns={3}
        />
      </Section>

      <Section title="Risk profile">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <RiskPill label="Risk count" value={metrics.riskCount} tone="rose" />
          <RiskPill label="Warnings" value={metrics.warningCount} tone="amber" />
          <RiskPill label="Critical issues" value={deal.critical_issues?.length ?? metrics.riskCount} tone="rose" />
          <RiskPill label="Due diligence" value={metrics.ddCount} tone="sky" />
        </div>
        {(deal.critical_issues?.length ?? 0) > 0 && (
          <ul className="mt-3 space-y-1 text-xs text-rose-200/90">
            {deal.critical_issues!.slice(0, 2).map((item) => (
              <li key={item} className="break-words rounded-md border border-rose-400/20 bg-rose-400/5 px-2 py-1">
                {item}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="AI summary">
        <p className="break-words text-sm leading-relaxed text-muted-foreground">{summary}</p>
      </Section>

      <div className="flex flex-wrap gap-2 border-t border-border/60 px-4 py-3">
        <ActionLink href={`/laundry/property/${deal.id}`} label="Open deal" />
        <ActionLink href={`/laundry/property/${deal.id}`} label="Open memo" icon={FileText} />
        {deal.listing_url && (
          <a
            href={deal.listing_url}
            target="_blank"
            rel="noreferrer"
            className={actionClass}
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open listing
          </a>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={actionClass}
          disabled={createExport.isPending}
          onClick={exportDeal}
        >
          {createExport.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <FileSpreadsheet className="h-3.5 w-3.5" />
          )}
          Export Excel
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn(actionClass, "text-rose-300 hover:text-rose-200")}
          disabled={del.isPending}
          onClick={deleteDeal}
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete
        </Button>
      </div>
    </article>
  );
}

const actionClass =
  "h-8 gap-1.5 rounded-md border border-border/60 bg-background/30 px-2.5 font-mono text-[10px] uppercase tracking-widest text-foreground hover:bg-background/60";

function ActionLink({
  href,
  label,
  icon: Icon,
}: {
  href: string;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <Link href={href} className={cn(actionClass, "inline-flex items-center")}>
      {Icon && <Icon className="h-3.5 w-3.5" />}
      {label}
    </Link>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-border/50 px-4 py-3 last:border-b-0">
      <h4 className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        {title}
      </h4>
      {children}
    </div>
  );
}

function MetricGrid({
  items,
  columns = 2,
}: {
  items: Array<{ label: string; value: React.ReactNode }>;
  columns?: 2 | 3;
}) {
  return (
    <dl
      className={cn(
        "grid gap-2",
        columns === 3 ? "grid-cols-1 sm:grid-cols-3" : "grid-cols-2 sm:grid-cols-3",
      )}
    >
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-lg border border-border/50 bg-background/20 px-3 py-2.5"
        >
          <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            {item.label}
          </dt>
          <dd className="mt-1 break-words text-base font-semibold tabular-nums text-foreground">
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function RiskPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone: "rose" | "amber" | "sky";
}) {
  const toneClass =
    tone === "rose"
      ? "border-rose-400/25 bg-rose-400/10 text-rose-200"
      : tone === "amber"
        ? "border-amber-400/25 bg-amber-400/10 text-amber-100"
        : "border-sky-400/25 bg-sky-400/10 text-sky-200";

  return (
    <div className={cn("rounded-lg border px-3 py-2 text-center", toneClass)}>
      <div className="font-mono text-[10px] uppercase tracking-widest opacity-80">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
