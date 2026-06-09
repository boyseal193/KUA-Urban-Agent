/**
 * K.U.A. — Laundry vertical API client.
 *
 * Mirrors the structure of `dealsApi` / `scanApi` but talks to the independent
 * `/laundry/*` routers on the FastAPI backend. Nothing in this file imports
 * from the storage API modules.
 */
import { api } from "./client";

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type LaundryPropertyType =
  | "existing_laundromat"
  | "empty_commercial"
  | "retail"
  | "mixed_use"
  | "industrial";

export type LaundryAcquisitionType = "buy" | "rent";

export type LaundrySearchType = "automatic_scan" | "manual_url" | "area_search";

export type LaundryDealStatus =
  | "approved_candidate"
  | "manual_review"
  | "rejected"
  | "extraction_failed"
  | "deleted"
  | (string & {});

export interface LaundryProperty {
  id: string;
  source?: string | null;
  listing_url?: string | null;
  address?: string | null;
  city?: string | null;
  neighbourhood?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  property_type?: LaundryPropertyType | null;
  acquisition_type?: LaundryAcquisitionType | null;
  floor_area_m2?: number | null;
  asking_price?: number | null;
  asking_rent_month?: number | null;
  rent_per_m2?: number | null;
  washer_count?: number | null;
  dryer_count?: number | null;
  ground_floor?: boolean | null;
  loading_access?: boolean | null;
  corner_unit?: boolean | null;
  water_available?: boolean | null;
  gas_available?: boolean | null;
  drainage_available?: boolean | null;
  three_phase_power?: boolean | null;
  description?: string | null;
  score?: number | null;
  verdict?: string | null;
  classification?: string | null;
  confidence_band?: string | null;
  deal_status: LaundryDealStatus;
  status: string;
  created_at?: string | null;
  deleted_at?: string | null;
  ceiling_height?: number | null;
  job_id?: string | null;
  ebitda_eur?: number | null;
  payback_years?: number | null;
  in_preferred_market?: boolean | null;
  matched_neighbourhood?: string | null;
  analysis_id?: string | null;
  has_memo?: boolean;
  memo_preview?: string | null;
  risk_flags?: string[];
}

export interface LaundryEconomics {
  acquisition_type: LaundryAcquisitionType;
  floor_area_m2: number;
  washer_count: number;
  dryer_count: number;
  expected_revenue_eur: number;
  steady_state_revenue_eur: number;
  annual_opex_eur: number;
  ebitda_eur: number;
  operating_margin: number;
  yield_pct: number | null;
  payback_years: number | null;
  irr_estimate_pct: number | null;
  total_investment_eur: number;
  capex_eur: number;
  machine_capex_eur: number;
  ancillary_capex_eur: number;
  fit_out_total_eur: number;
  construction_cost_eur: number;
  electrical_upgrades_eur: number;
  plumbing_upgrades_eur: number;
  ventilation_eur: number;
  drainage_upgrades_eur: number;
  gas_connection_eur: number;
  water_supply_eur: number;
  signage_branding_eur: number;
  legal_costs_eur: number;
  licensing_eur: number;
  initial_marketing_eur: number;
  initial_staff_setup_eur: number;
  working_capital_eur: number;
  electricity_cost_eur: number;
  gas_cost_eur: number;
  water_cost_eur: number;
  cleaning_cost_eur: number;
  supplies_cost_eur: number;
  payroll_cost_eur: number;
  maintenance_cost_eur: number;
  insurance_cost_eur: number;
  internet_cost_eur: number;
  waste_cost_eur: number;
  rent_cost_eur: number;
  break_even_revenue_eur: number;
  break_even_cycles_per_day: number | null;
  utilisation_factor: number;
  assumptions_version?: string;
  [key: string]: unknown;
}

export interface LaundryScoreResult {
  score: number;
  verdict: string;
  classification: string;
  deal_status: LaundryDealStatus;
  confidence: { band: string; pct: number; fields_present: number };
  auto_scores: {
    location_score: number;
    economics_score: number;
    physical_fit_score: number;
    competition_score: number;
    risk_score: number;
    sub_components: Record<string, number>;
  };
  drivers: Record<string, string[]>;
  notes: string[];
  weights_used: Record<string, number>;
  thresholds: { approved_min: number; manual_review_min: number };
}

export interface LaundryDueDiligence {
  strengths: string[];
  weaknesses: string[];
  opportunities: string[];
  threats: string[];
  red_flags: string[];
  risks: string[];
  due_diligence_checklist: string[];
  required_verification: string[];
  next_steps: string[];
  confidence: { band: string; pct: number; fields_present: number };
}

export interface LaundryLocationIntel {
  population_density_per_km2: number;
  apartment_density_pct: number;
  household_income_eur: number;
  students_within_1km: number;
  hotels_within_500m: number;
  universities_within_2km: number;
  nearby_laundromats_within_500m: number;
  competitors_within_1km: number;
  walkability_score_0_100: number;
  night_safety_0_100: number;
  growth_potential_0_100: number;
  street_visibility_0_100?: number;
  public_transport_score_0_100?: number;
  destination_intensity?: number;
  data_sources: string[];
  city?: string | null;
  neighbourhood?: string | null;
}

export interface LaundryAnalysis {
  id: string;
  property_id: string;
  input: Record<string, unknown>;
  location: LaundryLocationIntel;
  economics: LaundryEconomics;
  score: LaundryScoreResult;
  due_diligence: LaundryDueDiligence;
  assumptions_used: Record<string, unknown>;
  verdict?: string | null;
  classification?: string | null;
  deal_killer?: string | null;
  ic_memo?: string | null;
  created_at?: string | null;
}

export interface LaundryPropertyDetailResponse {
  success: boolean;
  property: LaundryProperty;
  latest_analysis: LaundryAnalysis | null;
}

export interface LaundryKpis {
  total_scanned: number;
  approved_count: number;
  manual_review_count: number;
  rejected_count: number;
  approval_rate: number;
  avg_score: number | null;
}

export interface LaundryScanListingResult {
  id?: string;
  job_id: string;
  listing_index: number;
  listing_url?: string | null;
  status: string;
  property_id?: string | null;
  deal_status?: LaundryDealStatus | null;
  score?: number | null;
  error_message?: string | null;
  result?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface LaundryScanSummary {
  scanned_count?: number;
  listings_total?: number;
  listings_done?: number;
  listings_failed?: number;
  approved_count?: number;
  manual_review_count?: number;
  rejected_count?: number;
  skipped_count?: number;
  extraction_failed_count?: number;
  persisted_count?: number;
  property_count?: number;
  listing_result_count?: number;
  results_missing?: boolean;
  summary_property_mismatch?: boolean;
  approved_candidates?: LaundryProperty[];
  manual_review_deals?: LaundryProperty[];
  rejected_deals?: LaundryProperty[];
  extraction_failed_deals?: LaundryProperty[];
}

export interface LaundryScanMemoRef {
  property_id: string;
  analysis_id?: string | null;
  address?: string | null;
  listing_url?: string | null;
  deal_status?: LaundryDealStatus | null;
  score?: number | null;
  memo_preview?: string | null;
}

export interface LaundryScanJob {
  id: string;
  status: string;
  search_type: LaundrySearchType;
  property_type?: LaundryPropertyType | null;
  acquisition_type?: LaundryAcquisitionType | null;
  search_url?: string | null;
  listing_limit: number;
  progress_pct: number;
  listings_total: number;
  listings_done: number;
  listings_failed: number;
  approved_count: number;
  manual_review_count: number;
  rejected_count: number;
  excel_path?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  payload?: Record<string, unknown> | null;
}

export interface LaundryScanStep {
  id: string;
  step_key: string;
  status: string;
  step_order: number;
  listing_index?: number | null;
  listing_url?: string | null;
  error_type?: string | null;
  error_message?: string | null;
  duration_ms?: number | null;
  payload?: Record<string, unknown>;
  created_at?: string | null;
}

export interface LaundryScanResponse {
  success: boolean;
  job: LaundryScanJob;
  steps: LaundryScanStep[];
  listings: LaundryScanListingResult[];
  properties: LaundryProperty[];
  memos: LaundryScanMemoRef[];
  summary: LaundryScanSummary;
  search_diagnostics?: LaundrySearchDiagnostics | null;
}

export interface LaundryLaunchScanPayload {
  property_type?: LaundryPropertyType | null;
  acquisition_type?: LaundryAcquisitionType | null;
  search_type: LaundrySearchType;
  /** Listing or area-search URL. ``search_url`` is still accepted by the backend for legacy clients. */
  listing_url?: string | null;
  /** Free-form listing text. ``seed_text`` is the legacy alias. */
  raw_listing_text?: string | null;
  listing_limit?: number;
  /** Queue on the ARQ worker (default). ``async_mode`` is the legacy alias. */
  run_in_background?: boolean;
  /** Run the LLM polish pass on the generated memo. ``polish_with_llm`` is the legacy alias. */
  llm_memo_polish?: boolean;
  /** Case-insensitive substring whitelist applied to address + city + neighbourhood. */
  neighbourhood_filters?: string[];
  /** Soft upper bound on floor area (m²) — oversized hits land in manual_review. */
  max_size_sqm?: number | null;
  min_size_sqm?: number | null;
  max_price_eur?: number | null;
  max_rent_month_eur?: number | null;
  city?: string | null;
  ground_floor_only?: boolean;
  /** When true and no listing_url provided, the backend auto-generates one from the filters. */
  auto_generate_url?: boolean;
  /** idealista | fotocasa | habitaclia | google_maps | custom */
  search_provider?: LaundrySearchProvider | null;
  search_provider_extras?: Record<string, string>;
  /** Shortcut to push weights/thresholds into ``overrides``. */
  scoring_overrides?: Record<string, unknown>;
  filters?: Record<string, unknown>;
  overrides?: Record<string, unknown>;
}

export type LaundrySearchProvider =
  | "idealista"
  | "fotocasa"
  | "habitaclia"
  | "google_maps"
  | "custom";

export interface LaundrySearchUrlPayload {
  acquisition_type: LaundryAcquisitionType;
  property_type: LaundryPropertyType;
  city?: string;
  neighbourhoods?: string[];
  max_size_sqm?: number | null;
  min_size_sqm?: number | null;
  max_price_eur?: number | null;
  max_rent_month_eur?: number | null;
  ground_floor_only?: boolean;
  listing_limit?: number;
  provider?: LaundrySearchProvider;
  extra_filters?: Record<string, string>;
}

export interface LaundrySearchDiagnostics {
  generated_url: string;
  listing_count?: number | null;
  fallback_level: string;
  stage: number;
  applied_filters: Record<string, string>;
  removed_filters: string[];
  pipeline_filters?: Record<string, unknown>;
  search_broadened?: boolean;
  broadening_reason?: string | null;
  attempts?: Array<{
    url: string;
    count: number;
    fallback_level: string;
    stage: number;
    removed_filters?: string[];
  }>;
}

export interface LaundrySearchUrlResult {
  success: boolean;
  provider: string;
  url: string;
  description: string;
  filters_applied: Record<string, string>;
  warnings: string[];
  search_diagnostics?: LaundrySearchDiagnostics;
  search_broadened?: boolean;
  broadening_reason?: string | null;
}

export interface LaundrySearchProviderInfo {
  key: LaundrySearchProvider | string;
  label: string;
}

export const LAUNDRY_PREFERRED_NEIGHBOURHOODS = [
  "Raval",
  "Sant Antoni",
  "Poble Sec",
  "Clot",
  "Hospitalet",
] as const;

export const LAUNDRY_DEFAULT_MAX_SQM = 80;

export const LAUNDRY_SEARCH_PROVIDERS: { value: LaundrySearchProvider; label: string }[] = [
  { value: "idealista", label: "Idealista" },
  { value: "fotocasa", label: "Fotocasa" },
  { value: "habitaclia", label: "Habitaclia" },
  { value: "google_maps", label: "Google Maps (research)" },
  { value: "custom", label: "Custom template" },
];

export interface LaundryExportRecord {
  id: string;
  format: string;
  file_path: string;
  size_bytes: number;
  created_at?: string | null;
  property_id?: string | null;
  job_id?: string | null;
  download_url: string;
}

export interface LaundrySettingsPayload {
  defaults: Record<string, unknown>;
  overrides: Record<string, unknown>;
  effective: Record<string, unknown>;
  notes?: string | null;
}

export interface LaundryMapMarker {
  id: string;
  lat: number;
  lng: number;
  score: number | null;
  deal_status: LaundryDealStatus;
  address?: string | null;
  city?: string | null;
  verdict?: string | null;
}

// ---------------------------------------------------------------------------
// API surface
// ---------------------------------------------------------------------------

export const laundryApi = {
  kpis: () => api<{ success: boolean; kpis: LaundryKpis }>(`/laundry/kpis`),

  top: (limit = 25) =>
    api<{ success?: boolean; top_deals?: LaundryProperty[]; deals?: LaundryProperty[] }>(
      `/laundry/deals/top`,
      { query: { limit } },
    ),
  approved: (limit = 50) =>
    api<{ success?: boolean; approved_candidates?: LaundryProperty[]; deals?: LaundryProperty[] }>(
      `/laundry/deals/approved`,
      { query: { limit } },
    ),
  manualReview: (limit = 50) =>
    api<{ success?: boolean; manual_review_deals?: LaundryProperty[]; deals?: LaundryProperty[] }>(
      `/laundry/deals/manual-review`,
      { query: { limit } },
    ),
  rejected: (limit = 50) =>
    api<{ success?: boolean; rejected_deals?: LaundryProperty[]; deals?: LaundryProperty[] }>(
      `/laundry/deals/rejected`,
      { query: { limit } },
    ),
  all: (limit = 100, offset = 0) =>
    api<{ deals: LaundryProperty[] }>(`/laundry/deals/all`, {
      query: { limit, offset },
    }),
  markers: (limit = 500) =>
    api<{ markers: LaundryMapMarker[] }>(`/laundry/map/markers`, { query: { limit } }),

  detail: (id: string) =>
    api<LaundryPropertyDetailResponse>(`/laundry/properties/${id}`),

  regenerateMemo: (id: string) =>
    api<{ success: boolean; property_id: string; ic_memo: string }>(
      `/laundry/properties/${id}/memo`,
      { method: "POST" },
    ),
  rescore: (id: string) =>
    api<{
      success: boolean;
      property_id: string;
      score: LaundryScoreResult;
      economics: LaundryEconomics;
    }>(`/laundry/properties/${id}/rescore`, { method: "POST" }),
  remove: (id: string, reason?: string) =>
    api<{ success: boolean; property: LaundryProperty }>(
      `/laundry/properties/${id}` + (reason ? `?reason=${encodeURIComponent(reason)}` : ""),
      { method: "DELETE" },
    ),
  restore: (id: string) =>
    api<{ success: boolean; property: LaundryProperty }>(
      `/laundry/properties/${id}/restore`,
      { method: "POST" },
    ),
  deleted: (limit = 100) =>
    api<{ success: boolean; properties: LaundryProperty[] }>(
      `/laundry/properties/deleted`,
      { query: { limit } },
    ),
  duplicates: (limit = 50) =>
    api<{
      success: boolean;
      clusters: Array<{
        dedupe_key: string;
        size: number;
        properties: Array<{
          id: string;
          address?: string | null;
          listing_url?: string | null;
          score?: number | null;
          deal_status: LaundryDealStatus;
        }>;
      }>;
      count: number;
    }>(`/laundry/properties/duplicates`, { query: { limit } }),

  analyse: (payload: { url?: string; text?: string; overrides?: Record<string, unknown>; polish_with_llm?: boolean }) =>
    api<Record<string, unknown>>(`/laundry/analyse`, {
      method: "POST",
      body: payload,
      timeoutMs: 600_000,
    }),

  launchScan: (payload: LaundryLaunchScanPayload) =>
    api<{
      success: boolean;
      async: boolean;
      job_id: string;
      status: string;
      websocket_url?: string;
      search_url?: string;
      auto_generated_url?: LaundrySearchUrlResult;
      search_diagnostics?: LaundrySearchDiagnostics;
      result?: Record<string, unknown>;
    }>(`/laundry/scans`, { method: "POST", body: payload, timeoutMs: 600_000 }),

  generateSearchUrl: (payload: LaundrySearchUrlPayload) =>
    api<LaundrySearchUrlResult>(`/laundry/search-url`, {
      method: "POST",
      body: payload,
      timeoutMs: 30_000,
    }),

  listSearchProviders: () =>
    api<{ success: boolean; providers: LaundrySearchProviderInfo[] }>(
      `/laundry/search-providers`,
    ),

  listScans: (limit = 50) =>
    api<{ scans: LaundryScanJob[] }>(`/laundry/scans`, { query: { limit } }),
  getScan: (id: string) => api<LaundryScanResponse>(`/laundry/scans/${id}`),
  resumeScan: (id: string) =>
    api<{ success: boolean; job_id: string; status: string }>(
      `/laundry/scans/${id}/resume`,
      { method: "POST" },
    ),

  createExport: (id: string, format: string) =>
    api<{
      success: boolean;
      export_id: string;
      format: string;
      file_path: string;
      filename: string;
      size_bytes: number;
      download_url: string;
    }>(`/laundry/properties/${id}/exports`, {
      method: "POST",
      body: { format },
      timeoutMs: 120_000,
    }),
  listExports: (limit = 100) =>
    api<{ success: boolean; exports: LaundryExportRecord[] }>(`/laundry/exports`, {
      query: { limit },
    }),
  exportFormats: () =>
    api<{ formats: string[] }>(`/laundry/exports/formats`),
  downloadExportUrl: (exportId: string) => `/api/proxy/laundry/exports/${exportId}/download`,

  adminStats: () =>
    api<{ success: boolean; stats: LaundryKpis }>(`/laundry/admin/stats`),
  purgeTestData: () =>
    api<{ success: boolean; deleted: number }>(`/laundry/admin/cleanup/test-data`, {
      method: "POST",
    }),
  bulkRescore: (payload: { deal_statuses?: string[]; limit?: number }) =>
    api<{ success: boolean; rescored: string[]; count: number }>(
      `/laundry/admin/bulk-rescore`,
      { method: "POST", body: payload },
    ),

  getSettings: () =>
    api<{ success: boolean } & LaundrySettingsPayload>(`/laundry/settings`),
  updateSettings: (payload: { overrides: Record<string, unknown>; notes?: string }) =>
    api<{ success: boolean; overrides: Record<string, unknown>; effective: Record<string, unknown> }>(
      `/laundry/settings`,
      { method: "PUT", body: payload },
    ),

  locationPreview: (
    params: { lat?: number | null; lng?: number | null; neighbourhood?: string; city?: string },
  ) =>
    api<{ success: boolean; location: LaundryLocationIntel; ts: string }>(
      `/laundry/location/preview`,
      {
        query: {
          lat: params.lat ?? undefined,
          lng: params.lng ?? undefined,
          neighbourhood: params.neighbourhood,
          city: params.city,
        },
      },
    ),
};
