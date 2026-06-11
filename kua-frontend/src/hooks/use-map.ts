"use client";

import { useQuery } from "@tanstack/react-query";

import { mapApi } from "@/lib/api/map";

export function useTacticalMapMarkers(limit = 500, vertical: "all" | "storage" | "laundry" = "all") {
  return useQuery({
    queryKey: ["tactical-map", vertical, limit],
    queryFn: () => mapApi.markers(limit, vertical, true),
    staleTime: 30_000,
  });
}
