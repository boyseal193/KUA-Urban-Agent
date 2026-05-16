"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import type { PropertyRecord } from "@/lib/api/types";

const Map = dynamic(() => import("./property-map"), {
  ssr: false,
  loading: () => (
    <Skeleton
      className="w-full"
      style={{ height: "calc(100vh - 220px)" }}
    />
  ),
});

export function PropertyMap(props: {
  deals: PropertyRecord[];
  height?: number | string;
}) {
  return <Map {...props} />;
}
