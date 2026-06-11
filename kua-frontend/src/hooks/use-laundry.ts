"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  laundryApi,
  type LaundryLaunchScanPayload,
  type LaundryPipelineExportScope,
  type LaundryProperty,
  type LaundryPropertyDetailResponse,
  type LaundryScanResponse,
} from "@/lib/api";

/** Laundry-only query keys — never reuse storage `deals` / `pipeline` keys. */
export const LAUNDRY_KEYS = {
  kpis: ["laundry", "kpis"] as const,
  top: (limit: number) => ["laundry", "top", limit] as const,
  approved: (limit: number) => ["laundry", "approved", limit] as const,
  manualReview: (limit: number) => ["laundry", "manual-review", limit] as const,
  rejected: (limit: number) => ["laundry", "rejected", limit] as const,
  all: (limit: number, offset: number) => ["laundry", "all", limit, offset] as const,
  detail: (id: string) => ["laundry", "detail", id] as const,
  markers: (limit: number) => ["laundry", "markers", limit] as const,
  scans: (limit: number) => ["laundry", "scans", limit] as const,
  scan: (id: string) => ["laundry", "scan", id] as const,
  exports: (limit: number) => ["laundry", "exports", limit] as const,
  duplicates: (limit: number) => ["laundry", "duplicates", limit] as const,
  deleted: (limit: number) => ["laundry", "deleted", limit] as const,
  settings: ["laundry", "settings"] as const,
};

function invalidateAllLaundryResults(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["laundry", "scans"] });
  qc.invalidateQueries({ queryKey: ["laundry", "scan"] });
  qc.invalidateQueries({ queryKey: ["laundry", "kpis"] });
  qc.invalidateQueries({ queryKey: ["laundry", "top"] });
  qc.invalidateQueries({ queryKey: ["laundry", "approved"] });
  qc.invalidateQueries({ queryKey: ["laundry", "manual-review"] });
  qc.invalidateQueries({ queryKey: ["laundry", "rejected"] });
  qc.invalidateQueries({ queryKey: ["laundry", "all"] });
  qc.invalidateQueries({ queryKey: ["laundry", "markers"] });
}

export function useLaundryKpis() {
  return useQuery({
    queryKey: LAUNDRY_KEYS.kpis,
    queryFn: () => laundryApi.kpis().then((r) => r.kpis),
    staleTime: 30_000,
  });
}

export function useLaundryTopDeals(limit = 25) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.top(limit),
    queryFn: () => laundryApi.top(limit).then((r) => r.top_deals ?? r.deals ?? []),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useLaundryApprovedDeals(limit = 50) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.approved(limit),
    queryFn: () => laundryApi.approved(limit).then((r) => r.approved_candidates ?? r.deals ?? []),
    staleTime: 15_000,
  });
}

export function useLaundryManualReview(limit = 50) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.manualReview(limit),
    queryFn: () => laundryApi.manualReview(limit).then((r) => r.manual_review_deals ?? r.deals ?? []),
    staleTime: 15_000,
  });
}

export function useLaundryRejected(limit = 50) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.rejected(limit),
    queryFn: () => laundryApi.rejected(limit).then((r) => r.rejected_deals ?? r.deals ?? []),
    staleTime: 30_000,
  });
}

export function useLaundryAllDeals(limit = 100, offset = 0) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.all(limit, offset),
    queryFn: () => laundryApi.all(limit, offset).then((r) => r.deals ?? []),
    staleTime: 15_000,
  });
}

export function useLaundryPipelineProperties(limit = 500) {
  return useQuery({
    queryKey: ["laundry", "pipeline", limit] as const,
    queryFn: () => laundryApi.properties({ limit }).then((r) => r.properties ?? []),
    staleTime: 15_000,
  });
}

export function useLaundryDetail(id: string | undefined) {
  return useQuery<LaundryPropertyDetailResponse>({
    queryKey: LAUNDRY_KEYS.detail(id ?? ""),
    queryFn: () => laundryApi.detail(id as string),
    enabled: Boolean(id),
  });
}

export function useLaundryMapMarkers(limit = 500) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.markers(limit),
    queryFn: () => laundryApi.markers(limit, true),
    staleTime: 30_000,
  });
}

export function useLaundryScans(limit = 50) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.scans(limit),
    queryFn: () => laundryApi.listScans(limit).then((r) => r.scans),
    staleTime: 5_000,
    refetchInterval: 10_000,
  });
}

export function useLaundryScan(id: string | undefined) {
  return useQuery<LaundryScanResponse>({
    queryKey: LAUNDRY_KEYS.scan(id ?? ""),
    queryFn: () => laundryApi.getScan(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.job?.status?.toLowerCase();
      if (!status || ["success", "completed", "failed", "no_results", "cancelled"].includes(status)) {
        return false;
      }
      return 4_000;
    },
  });
}

export function useLaundryExports(limit = 100) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.exports(limit),
    queryFn: () => laundryApi.listExports(limit).then((r) => r.exports),
  });
}

export function useLaundryDuplicates(limit = 50) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.duplicates(limit),
    queryFn: () => laundryApi.duplicates(limit),
  });
}

export function useLaundryDeleted(limit = 100) {
  return useQuery({
    queryKey: LAUNDRY_KEYS.deleted(limit),
    queryFn: () => laundryApi.deleted(limit).then((r) => r.properties),
  });
}

export function useLaundrySettings() {
  return useQuery({
    queryKey: LAUNDRY_KEYS.settings,
    queryFn: () => laundryApi.getSettings(),
  });
}

export function useLaunchLaundryScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LaundryLaunchScanPayload) => laundryApi.launchScan(payload),
    onSuccess: (_data, _vars, _ctx) => {
      invalidateAllLaundryResults(qc);
    },
  });
}

export function useRegenerateLaundryMemo(propertyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => laundryApi.regenerateMemo(propertyId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: LAUNDRY_KEYS.detail(propertyId) });
      invalidateAllLaundryResults(qc);
    },
  });
}

export function useRescoreLaundryProperty(propertyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => laundryApi.rescore(propertyId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: LAUNDRY_KEYS.detail(propertyId) });
      invalidateAllLaundryResults(qc);
    },
  });
}

export function useDeleteLaundryProperty() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      laundryApi.remove(id, reason),
    onSuccess: () => invalidateAllLaundryResults(qc),
  });
}

export function useRestoreLaundryProperty() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => laundryApi.restore(id),
    onSuccess: () => invalidateAllLaundryResults(qc),
  });
}

export function useCreateLaundryExport(propertyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (format: string) => laundryApi.createExport(propertyId, format),
    onSuccess: () => qc.invalidateQueries({ queryKey: LAUNDRY_KEYS.exports(100) }),
  });
}

export function useCreateLaundryPipelineExport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (scope: LaundryPipelineExportScope) => laundryApi.exportPipeline(scope),
    onSuccess: () => qc.invalidateQueries({ queryKey: LAUNDRY_KEYS.exports(100) }),
  });
}

export function useCreateLaundryScanExport(scanId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (scope: LaundryPipelineExportScope) => laundryApi.exportScan(scanId, scope),
    onSuccess: () => qc.invalidateQueries({ queryKey: LAUNDRY_KEYS.exports(100) }),
  });
}

export function useCreateLaundryBulkExport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      property_ids?: string[];
      scope?: LaundryPipelineExportScope;
    }) => laundryApi.exportBulk(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: LAUNDRY_KEYS.exports(100) }),
  });
}

export function useUpdateLaundrySettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { overrides: Record<string, unknown>; notes?: string }) =>
      laundryApi.updateSettings(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: LAUNDRY_KEYS.settings }),
  });
}

export function useBulkRescoreLaundry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { deal_statuses?: string[]; limit?: number }) =>
      laundryApi.bulkRescore(payload),
    onSuccess: () => invalidateAllLaundryResults(qc),
  });
}

export function usePurgeLaundryTestData() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => laundryApi.purgeTestData(),
    onSuccess: () => invalidateAllLaundryResults(qc),
  });
}

export type { LaundryProperty };
