/**
 * K.U.A. vertical switching utilities.
 *
 * The platform currently hosts two independent acquisition verticals:
 *
 *   * `storage`  — original self-storage pipeline (`/dashboard`, `/pipeline`, …)
 *   * `laundry`  — laundromat acquisition engine (`/laundry/*`)
 *
 * Each vertical owns its own routes, APIs, and database tables. The helpers in
 * this module are presentation-only: they figure out which vertical the
 * current URL belongs to and where the matching landing pages live.
 */

export type Vertical = "storage" | "laundry";

export const VERTICAL_META: Record<
  Vertical,
  {
    id: Vertical;
    label: string;
    short: string;
    accent: string;
    landing: string;
    description: string;
  }
> = {
  storage: {
    id: "storage",
    label: "Self Storage",
    short: "STORAGE",
    accent: "#38E1FF",
    landing: "/dashboard",
    description: "Urban self-storage acquisitions",
  },
  laundry: {
    id: "laundry",
    label: "Laundromats",
    short: "LAUNDRY",
    accent: "#A78BFA",
    landing: "/laundry/dashboard",
    description: "Laundromat acquisition engine",
  },
};

export function verticalFromPathname(pathname: string | null | undefined): Vertical {
  if (!pathname) return "storage";
  return pathname.startsWith("/laundry") ? "laundry" : "storage";
}

export function landingFor(vertical: Vertical): string {
  return VERTICAL_META[vertical].landing;
}
