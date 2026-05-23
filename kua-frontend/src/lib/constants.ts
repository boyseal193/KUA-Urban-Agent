import type { DealStatus, Verdict } from "./api/types";

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME || "KLAVE URBAN AGENT";
export const APP_SHORT = process.env.NEXT_PUBLIC_APP_SHORT || "K.U.A.";
export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || "0.1.0";

/** Barcelona city centroid — used as the default Mapbox/Leaflet center. */
export const BARCELONA_CENTER: [number, number] = [41.3879, 2.16992];

export const DEAL_STATUS_META: Record<
  string,
  {
    label: string;
    short: string;
    color: string;
    chipClass: string;
    bgClass: string;
    glow: string;
    description: string;
  }
> = {
  approved_candidate: {
    label: "Approved",
    short: "APPRV",
    color: "#7CFAB3",
    chipClass:
      "border-accent/40 bg-accent/10 text-accent",
    bgClass: "bg-accent/[0.05]",
    glow: "shadow-glow-neon",
    description: "Cleared for due diligence",
  },
  manual_review: {
    label: "Manual Review",
    short: "REVIEW",
    color: "#F5B400",
    chipClass:
      "border-kua-amber/40 bg-kua-amber/10 text-kua-amber",
    bgClass: "bg-kua-amber/[0.04]",
    glow: "",
    description: "Operator inspection required",
  },
  rejected: {
    label: "Rejected",
    short: "REJECT",
    color: "#FF4D6D",
    chipClass:
      "border-destructive/40 bg-destructive/10 text-destructive",
    bgClass: "bg-destructive/[0.04]",
    glow: "",
    description: "Failed underwriting threshold",
  },
};

export const VERDICT_META: Record<
  string,
  { label: string; color: string; chipClass: string }
> = {
  YES: {
    label: "YES",
    color: "#7CFAB3",
    chipClass: "border-accent/40 bg-accent/10 text-accent",
  },
  "MANUAL REVIEW": {
    label: "REVIEW",
    color: "#F5B400",
    chipClass: "border-kua-amber/40 bg-kua-amber/10 text-kua-amber",
  },
  NO: {
    label: "NO",
    color: "#FF4D6D",
    chipClass: "border-destructive/40 bg-destructive/10 text-destructive",
  },
  // ----- Legacy verdicts (pre kua-2.0) — preserved so old scans render -----
  "CONDITIONAL YES": {
    label: "COND.",
    color: "#38E1FF",
    chipClass: "border-primary/40 bg-primary/10 text-primary",
  },
  WEAK: {
    label: "WEAK",
    color: "#F5B400",
    chipClass: "border-kua-amber/40 bg-kua-amber/10 text-kua-amber",
  },
};

export function dealStatusMeta(status?: DealStatus | null) {
  return DEAL_STATUS_META[status ?? ""] ?? DEAL_STATUS_META.manual_review;
}

export function verdictMeta(verdict?: Verdict | null) {
  return VERDICT_META[verdict ?? ""] ?? VERDICT_META["MANUAL REVIEW"];
}

/**
 * Score → tier label mapping, aligned with the kua-2.0 scoring philosophy:
 *
 *   ≥ 75  → CORE (approved candidate, strong conviction)
 *   ≥ 40  → REVIEW (manual underwriting required)
 *   < 40  → REJECT
 */
export function scoreTier(score?: number | null) {
  if (score == null) return { label: "—", color: "#7C8699", glow: "" };
  if (score >= 75) return { label: "CORE", color: "#7CFAB3", glow: "shadow-glow-neon" };
  if (score >= 40) return { label: "REVIEW", color: "#F5B400", glow: "" };
  return { label: "REJECT", color: "#FF4D6D", glow: "" };
}

export const BARCELONA_DISTRICTS = [
  "Eixample",
  "Gràcia",
  "Les Corts",
  "Sant Gervasi",
  "Sarrià",
  "Poblenou",
  "Sants",
  "Clot",
  "Sant Martí",
  "Horta",
  "Guinardó",
  "Trinitat Vella",
  "Nou Barris",
  "Besòs",
  "Zona Franca",
  "Raval",
  "Gòtic",
  "Born",
] as const;

export const PROPERTY_TYPES = [
  { value: "locales", label: "Commercial Locals" },
  { value: "naves", label: "Industrial Naves" },
  { value: "oficinas", label: "Office Space" },
  { value: "garajes", label: "Garages" },
] as const;

export const BUILDING_TYPES = [
  "Commercial",
  "Warehouse",
  "Industrial",
  "Mixed-use",
  "Other",
] as const;

export const NAV_ITEMS = [
  { href: "/dashboard", label: "Command", icon: "LayoutGrid" },
  { href: "/pipeline", label: "Pipeline", icon: "Columns3" },
  { href: "/scan", label: "Live Scan", icon: "Radar" },
  { href: "/map", label: "Tactical Map", icon: "MapPinned" },
  { href: "/intelligence", label: "Intelligence", icon: "BrainCircuit" },
] as const;
