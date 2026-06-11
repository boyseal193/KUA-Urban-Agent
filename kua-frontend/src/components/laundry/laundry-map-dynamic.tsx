"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import type { LaundryMapMarker } from "@/lib/api";

const LaundryMap = dynamic(() => import("./laundry-map"), {
  ssr: false,
  loading: () => (
    <Skeleton className="w-full" style={{ height: "calc(100vh - 220px)" }} />
  ),
});

export function LaundryMapDynamic(props: {
  markers: LaundryMapMarker[];
  height?: number | string;
  missingCount?: number;
  totalCount?: number;
}) {
  return <LaundryMap {...props} />;
}
