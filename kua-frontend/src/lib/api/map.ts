import { api } from "./client";

export interface MapVerticalDiagnostics {
  vertical?: string;
  total_properties?: number;
  plotted?: number;
  missing_coordinates?: number;
  backfilled?: number;
  missing_samples?: Array<{
    id?: string;
    address?: string | null;
    city?: string | null;
    neighbourhood?: string | null;
    deal_status?: string | null;
  }>;
  google_api_key_configured?: boolean;
  provider_chain?: string[];
  error?: string;
}

export interface MapDiagnostics {
  total_markers?: number;
  plotted?: number;
  missing_coordinates?: number;
  google_api_key_configured?: boolean;
  provider_chain?: string[];
  verticals?: {
    storage?: MapVerticalDiagnostics;
    laundry?: MapVerticalDiagnostics;
  };
}

export interface TacticalMapMarker {
  id: string;
  vertical: "storage" | "laundry";
  lat: number;
  lng: number;
  latitude: number;
  longitude: number;
  score?: number | null;
  deal_status?: string | null;
  address?: string | null;
  city?: string | null;
  neighbourhood?: string | null;
  verdict?: string | null;
  geocode_source?: string | null;
}

export const mapApi = {
  markers: (limit = 500, vertical: "all" | "storage" | "laundry" = "all", backfill = true) =>
    api<{ success: boolean; markers: TacticalMapMarker[]; diagnostics: MapDiagnostics }>(
      `/map/markers`,
      { query: { limit, vertical, backfill } },
    ),

  diagnostics: (limit = 500) =>
    api<{ success: boolean; diagnostics: MapDiagnostics }>(`/map/diagnostics`, {
      query: { limit },
    }),
};
