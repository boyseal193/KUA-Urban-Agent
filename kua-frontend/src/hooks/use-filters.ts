"use client";

import { create } from "zustand";
import type { DealStatus } from "@/lib/api/types";

export interface FilterState {
  district: string | null;
  priceRange: [number, number];
  m2Range: [number, number];
  minYield: number; // decimal e.g. 0.08 = 8%
  status: DealStatus | "all";
  model: "all" | "freehold" | "lease";
  buildingType: string | null;
  loadingAccess: boolean | null;
  minCeilingHeight: number | null;
  search: string;
}

interface FilterActions {
  set: <K extends keyof FilterState>(key: K, value: FilterState[K]) => void;
  reset: () => void;
  patch: (patch: Partial<FilterState>) => void;
}

const initial: FilterState = {
  district: null,
  priceRange: [0, 2_000_000],
  m2Range: [0, 1000],
  minYield: 0,
  status: "all",
  model: "all",
  buildingType: null,
  loadingAccess: null,
  minCeilingHeight: null,
  search: "",
};

export const useFilters = create<FilterState & FilterActions>((set) => ({
  ...initial,
  set: (key, value) => set({ [key]: value } as Partial<FilterState>),
  patch: (patch) => set(patch),
  reset: () => set(initial),
}));
