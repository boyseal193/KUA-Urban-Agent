"use client";

import dynamic from "next/dynamic";
import { PropertyMap } from "@/components/map/property-map-dynamic";
import type { PropertyRecord } from "@/lib/api/types";

export function DealMiniMap({ property }: { property: PropertyRecord }) {
  if (!property.latitude || !property.longitude) {
    return (
      <div className="panel flex items-center justify-center p-10 text-xs text-muted-foreground">
        Coordinates unavailable for this property.
      </div>
    );
  }
  return <PropertyMap deals={[property]} height={300} />;
}

export default dynamic(() => Promise.resolve(DealMiniMap), { ssr: false });
