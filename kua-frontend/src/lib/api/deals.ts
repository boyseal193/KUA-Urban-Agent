import { api } from "./client";
import type {
  ApprovedDealsResponse,
  DealsByStatusResponse,
  DealStatus,
  ManualReviewResponse,
  PropertyDetailResponse,
  RejectedDealsResponse,
  TopDealsResponse,
} from "./types";

export const dealsApi = {
  top: (limit = 25) =>
    api<TopDealsResponse>(`/deals/top`, { query: { limit } }),

  approved: (limit = 50) =>
    api<ApprovedDealsResponse>(`/deals/approved`, { query: { limit } }),

  manualReview: (limit = 50) =>
    api<ManualReviewResponse>(`/deals/manual-review`, { query: { limit } }),

  rejected: (limit = 50) =>
    api<RejectedDealsResponse>(`/deals/rejected`, { query: { limit } }),

  byStatus: (status: DealStatus, limit = 50) =>
    api<DealsByStatusResponse>(`/deals/status/${status}`, { query: { limit } }),

  detail: (id: string) =>
    api<PropertyDetailResponse>(`/property/${id}`),

  regenerateMemo: (id: string) =>
    api<{ property_id: string; ic_memo: string }>(
      `/property/memo/${id}`,
      { method: "POST" }
    ),
};
