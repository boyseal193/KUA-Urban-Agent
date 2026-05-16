"use client";

import { useMemo } from "react";
import {
  useApprovedDeals,
  useManualReviewDeals,
  useRejectedDeals,
} from "./use-deals";
import type { PropertyRecord } from "@/lib/api/types";

export interface PortfolioKpis {
  totalScanned: number;
  approvedCount: number;
  manualReviewCount: number;
  rejectedCount: number;
  avgEbitdaYield: number | null;
  avgPaybackYears: number | null;
  totalInvestmentVolume: number;
  approvalRate: number;
  allDeals: PropertyRecord[];
  loading: boolean;
}

/**
 * Aggregates KPIs from the available `/deals/*` endpoints.
 * Yield/payback fields are not surfaced on the property record so
 * those numbers stream in over time as deals are opened (and the
 * analysis is cached). We default to null until enriched.
 */
export function usePortfolioKpis(): PortfolioKpis {
  const approved = useApprovedDeals(200);
  const manual = useManualReviewDeals(200);
  const rejected = useRejectedDeals(200);

  return useMemo(() => {
    const approvedDeals = approved.data ?? [];
    const manualDeals = manual.data ?? [];
    const rejectedDeals = rejected.data ?? [];
    const allDeals = [...approvedDeals, ...manualDeals, ...rejectedDeals];

    const totalScanned = allDeals.length;
    const approvedCount = approvedDeals.length;
    const manualReviewCount = manualDeals.length;
    const rejectedCount = rejectedDeals.length;

    const investmentVolume = allDeals.reduce(
      (acc, d) => acc + (Number(d.asking_price) || 0),
      0
    );

    const approvalRate =
      totalScanned > 0 ? approvedCount / totalScanned : 0;

    return {
      totalScanned,
      approvedCount,
      manualReviewCount,
      rejectedCount,
      avgEbitdaYield: null,
      avgPaybackYears: null,
      totalInvestmentVolume: investmentVolume,
      approvalRate,
      allDeals,
      loading: approved.isLoading || manual.isLoading || rejected.isLoading,
    };
  }, [approved, manual, rejected]);
}
