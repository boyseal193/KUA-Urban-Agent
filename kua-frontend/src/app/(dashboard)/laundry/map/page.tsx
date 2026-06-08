"use client";

import { PageHeader } from "@/components/common/page-header";
import { LaundryMapDynamic } from "@/components/laundry/laundry-map-dynamic";
import { StatusPill } from "@/components/common/status-pill";
import { useLaundryMapMarkers } from "@/hooks/use-laundry";

export default function LaundryMapPage() {
  const q = useLaundryMapMarkers(500);
  const count = q.data?.length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="LAUNDRY · TACTICAL MAP"
        title="Competition & Opportunity Map"
        subtitle="Every scanned laundromat plotted with score, verdict and competitor density."
        rightSlot={
          <>
            <StatusPill label={`${count} MARKERS`} color="#A78BFA" />
            <StatusPill label="CARTO · DARK MATTER" color="#7CFAB3" pulse={false} />
          </>
        }
      />

      <LaundryMapDynamic markers={q.data ?? []} />
    </div>
  );
}
