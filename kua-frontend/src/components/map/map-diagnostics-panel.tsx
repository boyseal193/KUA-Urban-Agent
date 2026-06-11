"use client";

import * as React from "react";
import { AlertTriangle, MapPin, CheckCircle2 } from "lucide-react";

import { GOOGLE_MAPS_CONFIGURED, loadGoogleMapsScript } from "@/lib/google-maps-config";
import type { MapDiagnostics } from "@/lib/api/map";

interface Props {
  diagnostics?: MapDiagnostics | null;
  plotted?: number;
  total?: number;
  className?: string;
}

export function MapDiagnosticsPanel({ diagnostics, plotted, total, className }: Props) {
  const [mapsJsOk, setMapsJsOk] = React.useState<boolean | null>(null);

  React.useEffect(() => {
    if (!GOOGLE_MAPS_CONFIGURED) {
      setMapsJsOk(false);
      return;
    }
    loadGoogleMapsScript().then(setMapsJsOk);
  }, []);

  const missing =
    diagnostics?.missing_coordinates ??
    Math.max((total ?? 0) - (plotted ?? 0), 0);
  const backendKey = diagnostics?.google_api_key_configured;
  const storage = diagnostics?.verticals?.storage;
  const laundry = diagnostics?.verticals?.laundry;

  return (
    <div
      className={
        "rounded-md border border-border/60 bg-card/80 px-4 py-3 text-xs backdrop-blur-xl " +
        (className ?? "")
      }
    >
      <div className="mb-2 flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        <MapPin className="h-3.5 w-3.5" />
        Map diagnostics
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <DiagRow label="Plotted" value={String(plotted ?? diagnostics?.plotted ?? 0)} ok />
        <DiagRow label="Missing coords" value={String(missing)} ok={missing === 0} />
        <DiagRow
          label="Backend geocoder"
          value={backendKey ? "GOOGLE_API_KEY set" : "Missing GOOGLE_API_KEY"}
          ok={Boolean(backendKey)}
        />
        <DiagRow
          label="Frontend Maps JS"
          value={
            !GOOGLE_MAPS_CONFIGURED
              ? "NEXT_PUBLIC_GOOGLE_MAPS_API_KEY missing"
              : mapsJsOk
                ? "Loaded"
                : mapsJsOk === false
                  ? "Failed to load"
                  : "Loading…"
          }
          ok={Boolean(GOOGLE_MAPS_CONFIGURED && mapsJsOk)}
        />
      </div>

      {(storage || laundry) && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {storage ? (
            <VerticalBlock
              label="Storage"
              total={storage.total_properties}
              plotted={storage.plotted}
              missing={storage.missing_coordinates}
              backfilled={storage.backfilled}
            />
          ) : null}
          {laundry ? (
            <VerticalBlock
              label="Laundry"
              total={laundry.total_properties}
              plotted={laundry.plotted}
              missing={laundry.missing_coordinates}
              backfilled={laundry.backfilled}
            />
          ) : null}
        </div>
      )}

      {missing > 0 && (
        <div className="mt-3 flex gap-2 text-amber-200">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
          <p className="leading-relaxed text-muted-foreground">
            {missing} propert{missing === 1 ? "y has" : "ies have"} no coordinates after geocoding.
            Set <span className="font-mono text-foreground">GOOGLE_API_KEY</span> on the backend and reload —
            the map endpoint backfills address + city automatically.
          </p>
        </div>
      )}
    </div>
  );
}

function DiagRow({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-start gap-2">
      {ok ? (
        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 text-emerald-400" />
      ) : (
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 text-amber-300" />
      )}
      <div>
        <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {label}
        </div>
        <div className="text-foreground">{value}</div>
      </div>
    </div>
  );
}

function VerticalBlock({
  label,
  total,
  plotted,
  missing,
  backfilled,
}: {
  label: string;
  total?: number;
  plotted?: number;
  missing?: number;
  backfilled?: number;
}) {
  return (
    <div className="rounded border border-border/50 bg-background/30 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-widest text-violet-200">{label}</div>
      <div className="mt-1 text-muted-foreground">
        {plotted ?? 0}/{total ?? 0} plotted · {missing ?? 0} missing
        {backfilled ? ` · ${backfilled} backfilled` : ""}
      </div>
    </div>
  );
}
