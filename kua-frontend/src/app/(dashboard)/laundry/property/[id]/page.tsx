"use client";

import { use, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Wand2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { LaundryScoreBadge } from "@/components/laundry/laundry-score-badge";
import { LaundryStatusBadge } from "@/components/laundry/laundry-status";
import {
  useCreateLaundryExport,
  useDeleteLaundryProperty,
  useLaundryDetail,
  useRegenerateLaundryMemo,
  useRescoreLaundryProperty,
} from "@/hooks/use-laundry";
import { money, moneyCompact, pct } from "@/lib/format";
import { laundryApi } from "@/lib/api";

const EXPORT_FORMATS = [
  { id: "excel", label: "Excel" },
  { id: "financial_model", label: "Financial Model" },
  { id: "csv", label: "CSV" },
  { id: "json", label: "JSON" },
  { id: "memo", label: "Memo (Markdown)" },
  { id: "zip", label: "ZIP" },
  { id: "full_package", label: "Full Package" },
];

export default function LaundryPropertyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const q = useLaundryDetail(id);
  const memoMut = useRegenerateLaundryMemo(id);
  const rescore = useRescoreLaundryProperty(id);
  const del = useDeleteLaundryProperty();
  const createExport = useCreateLaundryExport(id);
  const [downloading, setDownloading] = useState<string | null>(null);

  const detail = q.data;
  const p = detail?.property;
  const a = detail?.latest_analysis;
  const e = a?.economics;
  const dd = a?.due_diligence;
  const s = a?.score;
  const confidenceBand =
    p?.confidence_band ??
    (typeof s?.confidence === "object" ? s?.confidence?.band : undefined);

  if (!p) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="LAUNDRY · DEAL"
          title="Loading…"
          subtitle="Fetching property + latest analysis."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · DEAL"
        title={p.address || "Untitled laundromat"}
        subtitle={`${p.neighbourhood || "—"} · ${p.city || "—"} · ${(p.property_type || "").replace(/_/g, " ")}`}
        rightSlot={
          <Link
            href="/laundry/pipeline"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Pipeline
          </Link>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-xs">
            <div className="flex items-center gap-3">
              <LaundryScoreBadge score={p.score ?? null} size="lg" />
              <div className="space-y-1">
                <LaundryStatusBadge status={p.deal_status} />
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Confidence {confidenceBand ?? "—"}
                </div>
                <div className="text-foreground">{p.verdict ?? "—"}</div>
              </div>
            </div>

            <Row k="Classification" v={p.classification ?? "—"} />
            <Row k="Acquisition" v={(p.acquisition_type ?? "—").toUpperCase()} />
            <Row k="Floor area" v={`${p.floor_area_m2 ?? "—"} m²`} />
            <Row
              k="Asking / Rent"
              v={
                p.acquisition_type === "rent"
                  ? `${moneyCompact(p.asking_rent_month)}/mo`
                  : moneyCompact(p.asking_price)
              }
            />
            <Row k="Washer × Dryer" v={`${p.washer_count ?? "—"} × ${p.dryer_count ?? "—"}`} />
            {p.listing_url && (
              <a
                href={p.listing_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-violet-300 hover:underline"
              >
                Open listing <ExternalLink className="h-3 w-3" />
              </a>
            )}

            <div className="space-y-2 border-t border-border/60 pt-3">
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start"
                onClick={async () => {
                  await rescore.mutateAsync();
                  toast.success("Re-scored");
                }}
                disabled={rescore.isPending}
              >
                {rescore.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                Re-run economics & score
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start"
                onClick={async () => {
                  await memoMut.mutateAsync();
                  toast.success("Memo rebuilt");
                }}
                disabled={memoMut.isPending}
              >
                {memoMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                Rebuild memo
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start text-rose-300 hover:text-rose-200"
                onClick={async () => {
                  if (!confirm("Delete this property? Soft-delete only — can be restored.")) return;
                  await del.mutateAsync({ id });
                  toast.success("Deleted");
                }}
                disabled={del.isPending}
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete (soft)
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Investment view</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="memo">
              <TabsList>
                <TabsTrigger value="memo">Memo</TabsTrigger>
                <TabsTrigger value="economics">Economics</TabsTrigger>
                <TabsTrigger value="dd">Due Diligence</TabsTrigger>
                <TabsTrigger value="location">Location</TabsTrigger>
                <TabsTrigger value="exports">Exports</TabsTrigger>
              </TabsList>

              <TabsContent value="memo" className="prose prose-invert mt-4 max-w-none">
                {a?.ic_memo ? (
                  <article className="rounded-md border border-border/60 bg-card/40 p-4 text-xs leading-relaxed">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{a.ic_memo}</ReactMarkdown>
                  </article>
                ) : (
                  <p className="text-xs text-muted-foreground">No memo yet.</p>
                )}
              </TabsContent>

              <TabsContent value="economics" className="mt-4">
                {!e ? (
                  <p className="text-xs text-muted-foreground">No analysis yet.</p>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    <Stat k="Revenue (Y1)" v={money(e.expected_revenue_eur)} />
                    <Stat k="Steady-state" v={money(e.steady_state_revenue_eur)} />
                    <Stat k="Annual opex" v={money(e.annual_opex_eur)} />
                    <Stat k="EBITDA" v={money(e.ebitda_eur)} />
                    <Stat k="Margin" v={pct(e.operating_margin)} />
                    <Stat k="Yield" v={pct(e.yield_pct)} />
                    <Stat k="Payback" v={e.payback_years ? `${e.payback_years} yrs` : "—"} />
                    <Stat k="IRR (indicative)" v={e.irr_estimate_pct != null ? `${e.irr_estimate_pct}%` : "—"} />
                    <Stat k="Total investment" v={money(e.total_investment_eur)} />
                    <Stat k="Capex" v={money(e.capex_eur)} />
                    <Stat k="Machine capex" v={money(e.machine_capex_eur)} />
                    <Stat k="Fit-out" v={money(e.fit_out_total_eur)} />
                    <Stat k="Working capital" v={money(e.working_capital_eur)} />
                    <Stat k="Break-even rev" v={money(e.break_even_revenue_eur)} />
                    <Stat k="Cycles / day break-even" v={e.break_even_cycles_per_day != null ? `${e.break_even_cycles_per_day}` : "—"} />
                  </div>
                )}
              </TabsContent>

              <TabsContent value="dd" className="mt-4 space-y-4 text-xs">
                {!dd ? (
                  <p className="text-muted-foreground">No due-diligence package yet.</p>
                ) : (
                  <>
                    <Section title="Strengths" items={dd.strengths} tone="emerald" />
                    <Section title="Weaknesses" items={dd.weaknesses} tone="amber" />
                    <Section title="Opportunities" items={dd.opportunities} tone="violet" />
                    <Section title="Threats" items={dd.threats} tone="rose" />
                    <Section title="Red flags" items={dd.red_flags} tone="rose" />
                    <Section title="Required verification" items={dd.required_verification} tone="sky" />
                    <Section title="Recommended next steps" items={dd.next_steps} tone="emerald" />
                  </>
                )}
              </TabsContent>

              <TabsContent value="location" className="mt-4">
                {!a?.location ? (
                  <p className="text-xs text-muted-foreground">No location intel.</p>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {Object.entries(a.location)
                      .filter(([k]) => k !== "data_sources")
                      .map(([k, v]) => (
                        <Stat key={k} k={k.replace(/_/g, " ")} v={String(v ?? "—")} />
                      ))}
                    <div className="sm:col-span-2 lg:col-span-3 rounded-md border border-border/60 bg-card/40 p-3 text-[10px] font-mono text-muted-foreground">
                      Sources: {(a.location.data_sources ?? []).join(", ") || "baseline_only"}
                    </div>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="exports" className="mt-4">
                <div className="grid gap-2 sm:grid-cols-2">
                  {EXPORT_FORMATS.map((f) => (
                    <Button
                      key={f.id}
                      variant="ghost"
                      className="justify-between border border-border/60 bg-card/40"
                      onClick={async () => {
                        setDownloading(f.id);
                        try {
                          const res = await createExport.mutateAsync(f.id);
                          window.open(laundryApi.downloadExportUrl(res.export_id), "_blank");
                          toast.success(`${f.label} ready`);
                        } catch (err) {
                          toast.error((err as Error).message);
                        } finally {
                          setDownloading(null);
                        }
                      }}
                      disabled={downloading === f.id}
                    >
                      <span className="flex items-center gap-2">
                        <FileText className="h-3.5 w-3.5" />
                        {f.label}
                      </span>
                      {downloading === f.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Download className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  ))}
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {k}
      </span>
      <span className="text-foreground">{v}</span>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-md border border-border/60 bg-card/40 p-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{k}</div>
      <div className="mt-1 text-sm font-medium tabular-nums text-foreground">{v}</div>
    </div>
  );
}

function Section({
  title,
  items,
  tone,
}: {
  title: string;
  items?: string[];
  tone: "emerald" | "amber" | "rose" | "violet" | "sky";
}) {
  if (!items || items.length === 0) return null;
  const color =
    tone === "emerald"
      ? "border-emerald-400/30 text-emerald-200"
      : tone === "amber"
      ? "border-amber-400/30 text-amber-200"
      : tone === "rose"
      ? "border-rose-400/30 text-rose-200"
      : tone === "violet"
      ? "border-violet-400/30 text-violet-200"
      : "border-sky-400/30 text-sky-200";
  return (
    <div>
      <div className={`mb-2 font-mono text-[10px] uppercase tracking-widest ${color}`}>
        {title}
      </div>
      <ul className="space-y-1.5">
        {items.map((i, idx) => (
          <li key={idx} className="rounded-md border border-border/60 bg-card/40 px-3 py-2 text-xs text-foreground/90">
            {i}
          </li>
        ))}
      </ul>
    </div>
  );
}
