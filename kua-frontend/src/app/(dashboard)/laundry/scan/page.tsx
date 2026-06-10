"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Flame, Loader2, Sparkles, ExternalLink, Wand2 } from "lucide-react";
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
  LAUNDRY_SEARCH_PROVIDERS,
  laundryApi,
  type LaundryAcquisitionType,
  type LaundryOperationMode,
  type LaundryPropertyType,
  type LaundrySearchProvider,
  type LaundrySearchType,
  type LaundrySearchUrlResult,
  type LaundrySearchDiagnostics,
  type LaundryTimeoutLevel,
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
    help: "Generate the search URL from your filters and sweep every result.",
  },
];

const OPERATION_MODES: {
  value: LaundryOperationMode;
  label: string;
  help: string;
}[] = [
  {
    value: "conservative",
    label: "Conservative",
    help: "Fewer retries, stricter scoring, minimal search broadening.",
  },
  {
    value: "balanced",
    label: "Balanced",
    help: "Normal retries, scoring, and moderate broadening.",
  },
  {
    value: "aggressive",
    label: "Aggressive",
    help: "Broader searches, more retries, prefers manual review over reject.",
  },
];

const TIMEOUT_LEVELS: { value: LaundryTimeoutLevel; label: string }[] = [
  { value: "short", label: "Short (45s)" },
  { value: "normal", label: "Normal (90s)" },
  { value: "long", label: "Long (3m)" },
];

export default function LaundryScanPage() {
  const router = useRouter();
  const launch = useLaunchLaundryScan();

  const [propertyType, setPropertyType] =
    React.useState<LaundryPropertyType>("empty_commercial");
  const [acquisitionType, setAcquisitionType] =
    React.useState<LaundryAcquisitionType>("rent");
  const [searchType, setSearchType] =
    React.useState<LaundrySearchType>("automatic_scan");
  const [listingUrl, setListingUrl] = React.useState("");
  const [rawListingText, setRawListingText] = React.useState("");
  const [listingLimit, setListingLimit] = React.useState(20);
  const [runInBackground, setRunInBackground] = React.useState(true);
  const [llmMemoPolish, setLlmMemoPolish] = React.useState(false);
  const [maxSizeSqm, setMaxSizeSqm] = React.useState<number>(LAUNDRY_DEFAULT_MAX_SQM);
  const [neighbourhoodFilters, setNeighbourhoodFilters] = React.useState<string[]>([]);
  const [autoGenerateUrl, setAutoGenerateUrl] = React.useState(true);
  const [provider, setProvider] = React.useState<LaundrySearchProvider>("idealista");
  const [city] = React.useState("Barcelona");
  const [groundFloorOnly, setGroundFloorOnly] = React.useState(true);

  const [autonomousMode, setAutonomousMode] = React.useState(true);
  const [operationMode, setOperationMode] = React.useState<LaundryOperationMode>("balanced");
  const [maxAttempts, setMaxAttempts] = React.useState(3);
  const [concurrency, setConcurrency] = React.useState(2);
  const [timeoutLevel, setTimeoutLevel] = React.useState<LaundryTimeoutLevel>("normal");
  const [autoExport, setAutoExport] = React.useState(true);

  const [generatingUrl, setGeneratingUrl] = React.useState(false);
  const [generatedUrl, setGeneratedUrl] = React.useState<LaundrySearchUrlResult | null>(null);

  const helper = SEARCH_TYPES.find((s) => s.value === searchType)?.help ?? "";
  const requiresUrl = searchType === "manual_url" || searchType === "area_search";
  const canAutoGenerate = !requiresUrl || searchType === "area_search";

  function toggleNeighbourhood(label: string) {
    setNeighbourhoodFilters((prev) =>
      prev.includes(label) ? prev.filter((n) => n !== label) : [...prev, label],
    );
    setGeneratedUrl(null);
  }

  async function handleGenerateUrl(silent = false): Promise<LaundrySearchUrlResult | null> {
    setGeneratingUrl(true);
    try {
      const res = await laundryApi.generateSearchUrl({
        acquisition_type: acquisitionType,
        property_type: propertyType,
        city,
        neighbourhoods: neighbourhoodFilters,
        max_size_sqm: maxSizeSqm > 0 ? maxSizeSqm : null,
        ground_floor_only: groundFloorOnly,
        listing_limit: listingLimit,
        provider,
      });
      setGeneratedUrl(res);
      if (!silent) {
        toast.success(`Generated ${res.provider} search URL`);
        if (res.search_broadened) {
          toast.message("Search broadened automatically", {
            description:
              res.broadening_reason ?? "No listings found under original constraints",
          });
        }
        if (res.warnings?.length) {
          res.warnings.forEach((w) => toast.message(w));
        }
      }
      return res;
    } catch (err) {
      const msg = (err as Error).message || "Unable to generate search URL from selected filters.";
      if (!silent) toast.error(msg);
      return null;
    } finally {
      setGeneratingUrl(false);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();

    let effectiveUrl = listingUrl.trim();

    if (!effectiveUrl && canAutoGenerate && autoGenerateUrl && !rawListingText.trim()) {
      const built = await handleGenerateUrl(true);
      if (built) effectiveUrl = built.url;
    }

    if (requiresUrl && !effectiveUrl) {
      toast.error("Provide a listing URL for this scan type (or enable Auto-generate).");
      return;
    }
    if (!effectiveUrl && !rawListingText.trim() && !autoGenerateUrl) {
      toast.error("Enable Auto-generate URL or provide a listing URL / raw text.");
      return;
    }

    try {
      const res = await launch.mutateAsync({
        property_type: propertyType,
        acquisition_type: acquisitionType,
        search_type: searchType,
        listing_url: effectiveUrl || null,
        raw_listing_text: rawListingText.trim() || null,
        listing_limit: listingLimit,
        run_in_background: runInBackground,
        llm_memo_polish: llmMemoPolish,
        neighbourhood_filters: neighbourhoodFilters,
        max_size_sqm: maxSizeSqm > 0 ? maxSizeSqm : null,
        city,
        ground_floor_only: groundFloorOnly,
        auto_generate_url: autoGenerateUrl,
        search_provider: provider,
        autonomous_mode: autonomousMode,
        operation_mode: operationMode,
        max_attempts: maxAttempts,
        concurrency,
        timeout_level: timeoutLevel,
        auto_export: autoExport,
      });
      toast.success(`Scan ${res.status} — job ${res.job_id.slice(0, 8)}`);
      router.push(`/laundry/scans/${res.job_id}`);
    } catch (err) {
      toast.error((err as Error).message || "Failed to launch scan");
    }
  }

  // Reset preview when any URL-shaping field changes so the operator can't
  // launch a scan with a stale URL on screen.
  React.useEffect(() => {
    setGeneratedUrl(null);
  }, [propertyType, acquisitionType, provider, maxSizeSqm, groundFloorOnly, city]);

  React.useEffect(() => {
    let cancelled = false;
    laundryApi
      .getAutonomousSettings()
      .then((res) => {
        if (cancelled || !res.settings) return;
        const s = res.settings;
        setAutonomousMode(s.autonomous_mode);
        setOperationMode(s.operation_mode);
        setMaxAttempts(s.max_attempts);
        setConcurrency(s.concurrency);
        setTimeoutLevel(s.timeout_level);
        setAutoExport(s.auto_export);
      })
      .catch(() => {
        /* keep form defaults */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · NEW SCAN"
        title="Initiate Acquisition Scan"
        subtitle="Configure property type, acquisition mode and target neighbourhoods — the AI builds the search URL and underwrites every listing end-to-end."
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

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <Label className="tactical-mono mb-2 inline-block">Search type</Label>
                <Select value={searchType} onValueChange={(v) => setSearchType(v as LaundrySearchType)}>
                  <SelectTrigger>
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
              <div>
                <Label className="tactical-mono mb-2 inline-block">Search provider</Label>
                <Select value={provider} onValueChange={(v) => setProvider(v as LaundrySearchProvider)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LAUNDRY_SEARCH_PROVIDERS.map((p) => (
                      <SelectItem key={p.value} value={p.value}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  Broad city-wide search first — neighbourhood and size run in the pipeline. Ground floor is applied in the Idealista URL when enabled.
                </p>
              </div>
            </div>

            <div className="space-y-2 rounded-md border border-violet-400/20 bg-violet-400/[0.04] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <Sparkles className="h-4 w-4 text-violet-300" />
                  <div>
                    <Label htmlFor="auto-gen" className="text-xs uppercase tracking-widest text-violet-200">
                      Auto-generate URL from filters
                    </Label>
                    <p className="text-[11px] text-muted-foreground">
                      Build a broad {LAUNDRY_SEARCH_PROVIDERS.find(p => p.value === provider)?.label} search URL
                      from acquisition type and target neighbourhoods. Filters are applied progressively — never all at once in the URL.
                    </p>
                  </div>
                </div>
                <Switch
                  id="auto-gen"
                  checked={autoGenerateUrl}
                  onCheckedChange={setAutoGenerateUrl}
                />
              </div>
              <div className="flex flex-wrap items-center gap-2 pt-2">
                <Button
                  type="button"
                  variant="tactical"
                  size="sm"
                  onClick={() => handleGenerateUrl(false)}
                  disabled={generatingUrl}
                  className="bg-violet-500/10 text-violet-300 hover:bg-violet-500/20"
                >
                  {generatingUrl ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Generating…
                    </>
                  ) : (
                    <>
                      <Wand2 className="h-3.5 w-3.5" /> Generate Search URL
                    </>
                  )}
                </Button>
                {generatedUrl && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setListingUrl(generatedUrl.url);
                      toast.success("Generated URL copied into the URL field.");
                    }}
                  >
                    Use as URL
                  </Button>
                )}
              </div>

              {generatedUrl && (
                <div className="mt-2 space-y-2 rounded-md border border-violet-400/30 bg-background/40 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] uppercase tracking-widest text-violet-300">
                      {generatedUrl.description}
                    </p>
                    <a
                      href={generatedUrl.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-violet-300 hover:underline"
                    >
                      Open <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                  <code className="block break-all rounded bg-black/30 p-2 font-mono text-[11px] text-foreground">
                    {generatedUrl.url}
                  </code>
                  <SearchDiagnosticsPanel diagnostics={generatedUrl.search_diagnostics} />
                  {generatedUrl.warnings.length > 0 && (
                    <ul className="list-disc pl-4 text-[10px] text-amber-300/80">
                      {generatedUrl.warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label className="tactical-mono">
                Listing URL {requiresUrl ? "(required)" : "(optional override)"}
              </Label>
              <Input
                type="url"
                required={requiresUrl && !autoGenerateUrl}
                value={listingUrl}
                onChange={(e) => setListingUrl(e.target.value)}
                placeholder={
                  autoGenerateUrl
                    ? "Leave empty to auto-generate from filters"
                    : "https://www.idealista.com/en/local-…/"
                }
              />
            </div>

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
                Multiple selected → URL stays city-wide; pipeline narrows to preferred neighbourhoods.
              </p>
            </div>

            <div className="rounded-md border border-emerald-400/25 bg-emerald-400/[0.05] p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <Label htmlFor="ground-floor" className="text-xs uppercase tracking-widest text-emerald-200">
                    Ground floor only
                  </Label>
                  <p className="text-[11px] leading-relaxed text-muted-foreground">
                    Strong preference for laundromat sites. When enabled, Idealista URLs include the
                    <span className="font-mono text-foreground"> planta-baja </span>
                    filter. If that returns zero listings, the search automatically retries without the floor filter.
                  </p>
                </div>
                <Switch
                  checked={groundFloorOnly}
                  onCheckedChange={setGroundFloorOnly}
                  id="ground-floor"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
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
            </div>

            <div className="flex items-center gap-3">
              <Switch
                checked={llmMemoPolish}
                onCheckedChange={setLlmMemoPolish}
                id="polish-llm"
              />
              <Label htmlFor="polish-llm" className="text-xs">LLM memo polish</Label>
            </div>

            <div className="rounded-md border border-violet-400/25 bg-violet-400/[0.05] p-4 space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-violet-300" />
                    <Label htmlFor="autonomous-mode" className="text-xs uppercase tracking-widest text-violet-200">
                      Autonomous mode
                    </Label>
                  </div>
                  <p className="text-[11px] leading-relaxed text-muted-foreground">
                    Launch once — the AI sequencer runs URL generation, discovery broadening, scraping,
                    dedupe, extraction retries, scoring, memo, Excel export, and live pipeline updates
                    without manual babysitting.
                  </p>
                </div>
                <Switch
                  checked={autonomousMode}
                  onCheckedChange={setAutonomousMode}
                  id="autonomous-mode"
                />
              </div>

              {autonomousMode ? (
                <>
                  <div>
                    <Label className="tactical-mono mb-2 inline-block">Operation mode</Label>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                      {OPERATION_MODES.map((m) => (
                        <button
                          key={m.value}
                          type="button"
                          aria-pressed={operationMode === m.value}
                          onClick={() => setOperationMode(m.value)}
                          className={
                            "rounded-md border px-3 py-2 text-left text-xs transition " +
                            (operationMode === m.value
                              ? "border-violet-400/50 bg-violet-400/10 text-violet-200"
                              : "border-border/60 bg-card/40 text-muted-foreground hover:text-foreground")
                          }
                        >
                          <span className="font-medium">{m.label}</span>
                          <span className="mt-1 block text-[10px] leading-snug opacity-80">{m.help}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <div className="space-y-2">
                      <Label className="tactical-mono">Max attempts</Label>
                      <Input
                        type="number"
                        min={1}
                        max={10}
                        value={maxAttempts}
                        onChange={(e) => setMaxAttempts(Number(e.target.value) || 3)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="tactical-mono">Concurrency</Label>
                      <Input
                        type="number"
                        min={1}
                        max={8}
                        value={concurrency}
                        onChange={(e) => setConcurrency(Number(e.target.value) || 2)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="tactical-mono">Timeout</Label>
                      <Select
                        value={timeoutLevel}
                        onValueChange={(v) => setTimeoutLevel(v as LaundryTimeoutLevel)}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {TIMEOUT_LEVELS.map((t) => (
                            <SelectItem key={t.value} value={t.value}>
                              {t.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <Switch checked={autoExport} onCheckedChange={setAutoExport} id="auto-export" />
                    <Label htmlFor="auto-export" className="text-xs">
                      Auto-generate Excel export when scan completes
                    </Label>
                  </div>
                </>
              ) : null}
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
                {autoGenerateUrl && !listingUrl.trim() ? " The backend will auto-generate the URL on submit if the field is empty." : ""}
              </p>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function SearchDiagnosticsPanel({
  diagnostics,
}: {
  diagnostics?: LaundrySearchDiagnostics | null;
}) {
  if (!diagnostics) return null;

  const applied = Object.entries(diagnostics.applied_filters ?? {});
  const removed = diagnostics.removed_filters ?? [];

  return (
    <div className="mt-2 space-y-2 rounded border border-amber-400/20 bg-amber-400/[0.04] p-3 text-[11px]">
      {diagnostics.search_broadened && (
        <div>
          <p className="font-mono uppercase tracking-widest text-amber-200">
            Search broadened automatically
          </p>
          <p className="text-muted-foreground">
            Reason: {diagnostics.broadening_reason ?? "No listings found under original constraints"}
          </p>
        </div>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Listing count</p>
          <p>{diagnostics.listing_count ?? "—"}</p>
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Fallback level</p>
          <p className="capitalize">{diagnostics.fallback_level.replace(/_/g, " ")}</p>
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Stage</p>
          <p>{diagnostics.stage}</p>
        </div>
      </div>
      {applied.length > 0 && (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Applied filters (URL)</p>
          <ul className="mt-1 list-disc pl-4 text-muted-foreground">
            {applied.map(([k, v]) => (
              <li key={k}>
                {k}: {v != null && v !== "" ? String(v) : "—"}
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
