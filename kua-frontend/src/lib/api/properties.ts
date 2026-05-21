import { api } from "./client";

export interface DeletePropertyResponse {
  success: boolean;
  property?: Record<string, unknown> | null;
  error?: string | null;
  already_deleted?: boolean;
}

export interface RestorePropertyResponse {
  success: boolean;
  property?: Record<string, unknown> | null;
  error?: string | null;
  conflicting_property_id?: string | null;
  already_active?: boolean;
}

export interface DuplicateCluster {
  dedupe_key: string;
  size: number;
  properties: Array<{
    id: string;
    address?: string | null;
    listing_url?: string | null;
    score?: number | null;
    last_seen_at?: string | null;
  }>;
}

export const propertiesApi = {
  delete: (id: string, reason?: string) =>
    api<DeletePropertyResponse>(
      `/properties/${id}` + (reason ? `?reason=${encodeURIComponent(reason)}` : ""),
      { method: "DELETE", timeoutMs: 20_000 }
    ),

  restore: (id: string) =>
    api<RestorePropertyResponse>(`/properties/${id}/restore`, {
      method: "POST",
      timeoutMs: 20_000,
    }),

  bulkDelete: (ids: string[], reason?: string) =>
    api<{ success: boolean; deleted: number; errors: Array<{ id: string; error: string }> }>(
      `/properties/bulk-delete`,
      {
        method: "POST",
        body: { ids, reason },
        timeoutMs: 60_000,
      }
    ),

  duplicates: (limit = 50) =>
    api<{ success: boolean; clusters: DuplicateCluster[]; count: number }>(
      `/properties/duplicates`,
      { query: { limit }, timeoutMs: 30_000 }
    ),

  deleted: (limit = 100) =>
    api<{ success: boolean; properties: Array<Record<string, unknown>> }>(
      `/properties/deleted`,
      { query: { limit }, timeoutMs: 30_000 }
    ),
};

export const adminApi = {
  stats: () =>
    api<{ success: boolean; stats: Record<string, number | null> }>(`/admin/stats`, {
      timeoutMs: 20_000,
    }),

  purgeTestData: () =>
    api<{ success: boolean; deleted: number; errors: unknown[] }>(`/admin/cleanup/test-data`, {
      method: "POST",
      timeoutMs: 60_000,
    }),

  purgeFailedJobs: (olderThanDays = 1) =>
    api<{ success: boolean; deleted: number }>(`/admin/cleanup/failed-jobs`, {
      method: "POST",
      query: { older_than_days: olderThanDays },
      timeoutMs: 60_000,
    }),

  purgeOrphans: () =>
    api<{ success: boolean; deleted: Record<string, number> }>(`/admin/cleanup/orphans`, {
      method: "POST",
      timeoutMs: 60_000,
    }),
};
