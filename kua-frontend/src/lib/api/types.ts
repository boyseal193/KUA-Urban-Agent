/**
 * K.U.A. — Typed contracts for the FastAPI backend.
 *
 * These mirror the responses produced by the FastAPI service in
 * `main.py`, `economics.py`, `auto_scoring.py`, and `memo.py`.
 *
 * Keep this file as the single source of truth for shapes that cross
 * the network boundary. Add new fields here first, then propagate.
 */

export type Verdict = "YES" | "CONDITIONAL YES" | "WEAK" | "NO" | (string & {});

export type DealStatus =
  | "approved_candidate"
  | "manual_review"
  | "rejected"
  | (string & {});

export type ModelType = "freehold" | "lease" | (string & {});

export interface AutoScoreBreakdown {
  location_score: number;
  building_score: number;
  economics_score: number;
  risk_score: number;
  strategic_fit_score: number;
}

export interface DealScore {
  score: number;
  verdict: Verdict;
  classification: string;
  deal_killer: string | null;
  due_diligence_flags: string[];
  auto_scores: AutoScoreBreakdown;
}

export interface DealEconomics {
  model_type: ModelType;
  storage_revenue_per_m2_month: number;
  occupancy_rate: number;
  nra_efficiency: number;
  nra_m2: number;
  estimated_units: number;
  monthly_revenue: number;
  annual_revenue: number;
  annual_rent: number;
  annual_opex: number;
  ebitda: number;
  margin: number;
  asking_price: number;
  conversion_capex: number;
  total_investment: number;
  ebitda_yield: number | null;
  true_ebitda_yield: number | null;
  payback_years: number | null;
  true_payback_years: number | null;
}

export interface PropertyExtracted {
  source?: string | null;
  listing_url?: string | null;
  address?: string | null;
  city?: string | null;
  neighbourhood?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  gba_m2?: number | null;
  asking_price?: number | null;
  asking_rent_month?: number | null;
  rent_per_m2?: number | null;
  ceiling_height?: number | null;
  loading_access?: boolean | null;
  access_type?: string | null;
  floor_level?: string | null;
  building_type?: string | null;
  current_use?: string | null;
  description?: string | null;
  price_per_m2_nra?: number | null;
  nra_efficiency?: number | null;
}

/**
 * Row stored in the Supabase `properties` table and returned by GET /deals/*.
 */
export interface PropertyRecord extends PropertyExtracted {
  id: string;
  created_at?: string;
  status?: string;
  score?: number | null;
  verdict?: Verdict | null;
  classification?: string | null;
  deal_status?: DealStatus;
}

export interface AnalysisRecord {
  id: string;
  property_id: string;
  created_at?: string;
  input: PropertyExtracted;
  economics: DealEconomics;
  score: DealScore;
  verdict: Verdict;
  classification: string;
  deal_killer: string | null;
  ic_memo: string;
}

/** Full pipeline result returned by /analyse and embedded in scan results. */
export interface AnalysisResult {
  success?: boolean;
  error?: string;
  property_id?: string;
  extracted?: PropertyExtracted;
  coordinates?: { lat: number | null; lng: number | null };
  auto_scores?: DealScore;
  economics?: DealEconomics;
  score?: DealScore;
  deal_status?: DealStatus;
  ic_memo?: string;
  source_url?: string;
  scrape_preview?: string;
}

/** GET /property/{id} */
export interface PropertyDetailResponse {
  success: boolean;
  property?: PropertyRecord;
  latest_analysis?: AnalysisRecord | null;
  error?: string;
}

/** GET /deals/top */
export interface TopDealsResponse {
  top_deals: PropertyRecord[];
}
export interface ApprovedDealsResponse {
  approved_candidates: PropertyRecord[];
}
export interface ManualReviewResponse {
  manual_review_deals: PropertyRecord[];
}
export interface RejectedDealsResponse {
  rejected_deals: PropertyRecord[];
}
export interface DealsByStatusResponse {
  deals: PropertyRecord[];
}

/** POST /scan/idealista[+auto] */
export interface ScanResponse {
  success: boolean;
  error?: string;
  search_url_used?: string;
  scanned_count: number;
  approved_candidates_count: number;
  manual_review_count: number;
  top_deals_count: number;
  rejected_count: number;
  approved_candidates: AnalysisResult[];
  manual_review_deals: AnalysisResult[];
  top_deals: AnalysisResult[];
  rejected_history: AnalysisResult[];
  all_results: AnalysisResult[];
  excel_export_generated: boolean;
  excel_export_path?: string;
  excel_export_error?: string;
  filters_used?: Record<string, unknown>;
}

export interface AutoScanFilters {
  city_slug?: string;
  max_price?: number;
  min_m2?: number;
  max_m2?: number;
  property_types?: string[];
  ground_floor_only?: boolean;
  sale_only?: boolean;
  limit?: number;
  generate_excel?: boolean;
}

/** Auth */
export interface AuthSessionUser {
  username: string;
  displayName: string;
  clearance: string;
  issuedAt: number;
  expiresAt: number;
}

export interface AuthSessionResponse {
  authenticated: boolean;
  user: AuthSessionUser | null;
}
