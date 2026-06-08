"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Flame, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useLaunchLaundryScan } from "@/hooks/use-laundry";
import {
  LAUNDRY_DEFAULT_MAX_SQM,
  LAUNDRY_PREFERRED_NEIGHBOURHOODS,
  type LaundryAcquisitionType,
  type LaundryPropertyType,
  type LaundrySearchType,
} from "@/lib/api";

const PROPERTY_TYPES: { value: LaundryPropertyType; label: string }[] = [
  { value: "existing_laundromat", label: "Existing laundromat" },
  { value: "empty_commercial", label: "Empty commercial premises" },
  { value: "retail", label: "Retail premises" },
  { value: "mixed_use", label: "Mixed use" },
  { value: "industrial", label: "Industrial unit" },
];

const ACQUISITION_TYPES: { value: LaundryAcquisitionType; label: string }[] = [
  { value: "buy", label: "Buy" },
  { value: "rent", label: "Rent" },
];

const SEARCH_TYPES: { value: LaundrySearchType; label: string; help: string }[] = [
  {
    value: "manual_url",
    label: "Manual URL",
    help: "Paste a single listing URL — analyse one property end-to-end.",
  },
  {
    value: "area_search",
    label: "Area search",
    help: "Paste a search-results URL — every detail link is enqueued.",
  },
  {
    value: "automatic_scan",
    label: "Automatic scan",
    help: "Run the configured seed sweep across allowed sources.",
  },
];

export default function LaundryScanPage() {
  const router = useRouter();
  const launch = useLaunchLaundryScan();

  const [propertyType, setPropertyType] =
    React.useState<LaundryPropertyType>("empty_commercial");
  const [acquisitionType, setAcquisitionType] =
    React.useState<LaundryAcquisitionType>("rent");
  const [searchType, setSearchType] =
    React.useState<LaundrySearchType>("manual_url");
  const [listingUrl, setListingUrl] = React.useState("");
  const [rawListingText, setRawListingText] = React.useState("");
  const [listingLimit, setListingLimit] = React.useState(20);
  const [runInBackground, setRunInBackground] = React.useState(true);
  const [llmMemoPolish, setLlmMemoPolish] = React.useState(false);
  const [maxSizeSqm, setMaxSizeSqm] = React.useState<number>(LAUNDRY_DEFAULT_MAX_SQM);
  const [neighbourhoodFilters, setNeighbourhoodFilters] = React.useState<string[]>([]);

  const helper = SEARCH_TYPES.find((s) => s.value === searchType)?.help ?? "";

  function toggleNeighbourhood(label: string) {
    setNeighbourhoodFilters((prev) =>
      prev.includes(label) ? prev.filter((n) => n !== label) : [...prev, label],
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if ((searchType === "manual_url" || searchType === "area_search") && !listingUrl.trim()) {
      toast.error("Provide a listing URL for this scan type.");
      return;
    }
    try {
      const res = await launch.mutateAsync({
        property_type: propertyType,
        acquisition_type: acquisitionType,
        search_type: searchType,
        listing_url: listingUrl.trim() || null,
        raw_listing_text: rawListingText.trim() || null,
        listing_limit: listingLimit,
        run_in_background: runInBackground,
        llm_memo_polish: llmMemoPolish,
        neighbourhood_filters: neighbourhoodFilters,
        max_size_sqm: maxSizeSqm > 0 ? maxSizeSqm : null,
      });
      toast.success(`Scan ${res.status} — job ${res.job_id.slice(0, 8)}`);
      router.push(`/laundry/scans/${res.job_id}`);
    } catch (err) {
      toast.error((err as Error).message || "Failed to launch scan");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · NEW SCAN"
        title="Initiate Acquisition Scan"
        subtitle="Configure property type, acquisition mode and source — the AI underwrites every listing end-to-end."
      />

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Scan options</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-6">
            <div>
              <Label className="tactical-mono mb-2 inline-block">Property type</Label>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                {PROPERTY_TYPES.map((p) => (
                  <button
                    key={p.value}
                    type="button"
                    aria-pressed={propertyType === p.value}
                    onClick={() => setPropertyType(p.value)}
                    className={
                      "rounded-md border px-3 py-2 text-left text-xs transition " +
                      (propertyType === p.value
                        ? "border-violet-400/50 bg-violet-400/10 text-violet-200"
                        : "border-border/60 bg-card/40 text-muted-foreground hover:text-foreground")
                    }
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <Label className="tactical-mono mb-2 inline-block">Acquisition type</Label>
              <div className="grid grid-cols-2 gap-2 max-w-sm">
                {ACQUISITION_TYPES.map((a) => (
                  <button
                    key={a.value}
                    type="button"
                    aria-pressed={acquisitionType === a.value}
                    onClick={() => setAcquisitionType(a.value)}
                    className={
                      "rounded-md border px-3 py-2 text-center text-xs uppercase tracking-widest transition " +
                      (acquisitionType === a.value
                        ? "border-violet-400/50 bg-violet-400/10 text-violet-200"
                        : "border-border/60 bg-card/40 text-muted-foreground hover:text-foreground")
                    }
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <Label className="tactical-mono mb-2 inline-block">Search type</Label>
              <Select value={searchType} onValueChange={(v) => setSearchType(v as LaundrySearchType)}>
                <SelectTrigger className="max-w-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SEARCH_TYPES.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {helper && (
                <p className="mt-2 text-[11px] text-muted-foreground">{helper}</p>
              )}
            </div>

            {(searchType === "manual_url" || searchType === "area_search" || searchType === "automatic_scan") && (
              <div className="space-y-2">
                <Label className="tactical-mono">Listing URL</Label>
                <Input
                  type="url"
                  required={searchType !== "automatic_scan"}
                  value={listingUrl}
                  onChange={(e) => setListingUrl(e.target.value)}
                  placeholder="https://www.idealista.com/en/local-…/"
                />
              </div>
            )}

            <div className="space-y-2">
              <Label className="tactical-mono">Raw listing text (optional)</Label>
              <textarea
                value={rawListingText}
                onChange={(e) => setRawListingText(e.target.value)}
                rows={5}
                placeholder="Paste a listing description, broker email, or marketing PDF text…"
                className="w-full rounded-md border border-border/60 bg-background/40 p-3 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-violet-400/40"
              />
            </div>

            <div>
              <Label className="tactical-mono mb-2 inline-block">
                Preferred neighbourhoods (Barcelona)
              </Label>
              <div className="flex flex-wrap gap-2">
                {LAUNDRY_PREFERRED_NEIGHBOURHOODS.map((label: string) => {
                  const active = neighbourhoodFilters.includes(label);
                  return (
                    <button
                      key={label}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleNeighbourhood(label)}
                      className={
                        "rounded-full border px-3 py-1 text-[11px] uppercase tracking-widest transition " +
                        (active
                          ? "border-violet-400/50 bg-violet-400/15 text-violet-200"
                          : "border-border/60 bg-card/40 text-muted-foreground hover:text-foreground")
                      }
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">
                When at least one is selected only listings matching the address/city/neighbourhood pass.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
              <div className="space-y-2">
                <Label className="tactical-mono">Listing limit</Label>
                <Input
                  type="number"
                  min={1}
                  max={200}
                  value={listingLimit}
                  onChange={(e) => setListingLimit(Number(e.target.value) || 20)}
                />
              </div>
              <div className="space-y-2">
                <Label className="tactical-mono">Max size (m²)</Label>
                <Input
                  type="number"
                  min={0}
                  max={1000}
                  value={maxSizeSqm}
                  onChange={(e) => setMaxSizeSqm(Number(e.target.value) || 0)}
                />
                <p className="text-[10px] text-muted-foreground">
                  Right-sized urban units sit around 60–80 m². Larger hits go to manual review.
                </p>
              </div>
              <div className="flex items-center gap-3 pt-7">
                <Switch
                  checked={runInBackground}
                  onCheckedChange={setRunInBackground}
                  id="async-mode"
                />
                <Label htmlFor="async-mode" className="text-xs">Run in background</Label>
              </div>
              <div className="flex items-center gap-3 pt-7">
                <Switch
                  checked={llmMemoPolish}
                  onCheckedChange={setLlmMemoPolish}
                  id="polish-llm"
                />
                <Label htmlFor="polish-llm" className="text-xs">LLM memo polish</Label>
              </div>
            </div>

            <div className="flex items-center gap-3 border-t border-border/60 pt-4">
              <Button
                type="submit"
                variant="tactical"
                disabled={launch.isPending}
                className="bg-violet-500/10 text-violet-300 hover:bg-violet-500/20"
              >
                {launch.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Queuing…
                  </>
                ) : (
                  <>
                    <Flame className="h-3.5 w-3.5" /> Launch scan
                  </>
                )}
              </Button>
              <p className="text-[11px] text-muted-foreground">
                Async jobs persist across page reload, worker restart and browser close.
              </p>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
