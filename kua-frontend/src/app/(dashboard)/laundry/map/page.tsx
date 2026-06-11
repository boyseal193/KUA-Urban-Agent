"use client";

import { PageHeader } from "@/components/common/page-header";
import { MapDiagnosticsPanel } from "@/components/map/map-diagnostics-panel";
import { LaundryMapDynamic } from "@/components/laundry/laundry-map-dynamic";
import { StatusPill } from "@/components/common/status-pill";
import { useLaundryMapMarkers } from "@/hooks/use-laundry";

export default function LaundryMapPage() {
  const q = useLaundryMapMarkers(500);
  const markers = q.data?.markers ?? [];
  const diagnostics = q.data?.diagnostics;
  const plotted = markers.filter(
    (m) => typeof m.lat === "number" && typeof m.lng === "number",
  ).length;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · TACTICAL MAP"
        title="Competition & Opportunity Map"
        subtitle="Every scanned laundromat plotted with score, verdict and competitor density."
        rightSlot={
          <>
            <StatusPill label={`${plotted} MARKERS`} color="#A78BFA" />
            <StatusPill label="GEOCODED ON LOAD" color="#7CFAB3" pulse={false} />
          </>
        }
      />

      <MapDiagnosticsPanel
        diagnostics={
          diagnostics
            ? {
                plotted: diagnostics.plotted,
                missing_coordinates: diagnostics.missing_coordinates,
                google_api_key_configured: diagnostics.google_api_key_configured,
                provider_chain: diagnostics.provider_chain,
                verticals: { laundry: diagnostics },
              }
            : null
        }
        plotted={plotted}
        total={diagnostics?.total_properties ?? markers.length}
      />

      <LaundryMapDynamic
        markers={markers}
        missingCount={diagnostics?.missing_coordinates ?? 0}
        totalCount={diagnostics?.total_properties ?? markers.length}
      />
    </div>
  );
}
