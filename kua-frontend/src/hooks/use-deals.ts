"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { dealsApi } from "@/lib/api/deals";
import type { DealStatus } from "@/lib/api/types";
import { staleProperties } from "@/lib/stale-properties";

export const dealKeys = {
  all: ["deals"] as const,
  top: (limit?: number) => [...dealKeys.all, "top", limit] as const,
  approved: (limit?: number) => [...dealKeys.all, "approved", limit] as const,
  manual: (limit?: number) => [...dealKeys.all, "manual", limit] as const,
  rejected: (limit?: number) => [...dealKeys.all, "rejected", limit] as const,
  byStatus: (status: DealStatus, limit?: number) =>
    [...dealKeys.all, "status", status, limit] as const,
  detail: (id: string) => [...dealKeys.all, "detail", id] as const,
};

/** Drop any rows whose property has been removed (deleted_at IS NOT NULL). */
function withoutStale<T extends { id?: string | null; deleted_at?: unknown }>(
  rows: T[] | null | undefined
): T[] {
  if (!Array.isArray(rows)) return [];
  return rows.filter((r) => {
    if (!r) return false;
    if (r.deleted_at != null) return false;
    return !staleProperties.has(r.id ?? null);
  });
}

export function useApprovedDeals(limit = 50) {
  return useQuery({
    queryKey: dealKeys.approved(limit),
    queryFn: () => dealsApi.approved(limit),
    select: (d) => withoutStale(d.approved_candidates ?? []),
  });
}

export function useManualReviewDeals(limit = 50) {
  return useQuery({
    queryKey: dealKeys.manual(limit),
    queryFn: () => dealsApi.manualReview(limit),
    select: (d) => withoutStale(d.manual_review_deals ?? []),
  });
}

export function useRejectedDeals(limit = 50) {
  return useQuery({
    queryKey: dealKeys.rejected(limit),
    queryFn: () => dealsApi.rejected(limit),
    select: (d) => withoutStale(d.rejected_deals ?? []),
  });
}

export function useTopDeals(limit = 25) {
  return useQuery({
    queryKey: dealKeys.top(limit),
    queryFn: () => dealsApi.top(limit),
    select: (d) => withoutStale(d.top_deals ?? []),
  });
}

export function usePropertyDetail(id?: string) {
  return useQuery({
    queryKey: dealKeys.detail(id ?? ""),
    queryFn: () => dealsApi.detail(id!),
    enabled: !!id,
  });
}

export function useRegenerateMemo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => dealsApi.regenerateMemo(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: dealKeys.detail(id) });
    },
  });
}
