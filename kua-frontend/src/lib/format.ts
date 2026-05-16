/**
 * Display formatters that match the conventions used in the FastAPI memo
 * generator (`memo.py::money / pct / num`).
 */

const EUR = new Intl.NumberFormat("en-EU", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const EUR_COMPACT = new Intl.NumberFormat("en-EU", {
  style: "currency",
  currency: "EUR",
  notation: "compact",
  maximumFractionDigits: 1,
});

const PCT = new Intl.NumberFormat("en-EU", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const NUM = new Intl.NumberFormat("en-EU", {
  maximumFractionDigits: 2,
});

const INT = new Intl.NumberFormat("en-EU", {
  maximumFractionDigits: 0,
});

export function money(value: number | null | undefined, fallback = "—"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return EUR.format(Number(value));
}

export function moneyCompact(
  value: number | null | undefined,
  fallback = "—"
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return EUR_COMPACT.format(Number(value));
}

export function pct(
  value: number | null | undefined,
  fallback = "—"
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return PCT.format(Number(value));
}

export function num(
  value: number | null | undefined,
  fallback = "—"
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return NUM.format(Number(value));
}

export function int(
  value: number | null | undefined,
  fallback = "—"
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return INT.format(Number(value));
}

export function yearsLabel(value: number | null | undefined, fallback = "—"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return `${NUM.format(Number(value))} yrs`;
}

export function metersLabel(value: number | null | undefined, fallback = "—"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return fallback;
  return `${INT.format(Number(value))} m²`;
}

export function timeAgo(input: string | number | Date | null | undefined): string {
  if (!input) return "—";
  const d = new Date(input);
  const diff = Date.now() - d.getTime();
  if (Number.isNaN(diff)) return "—";

  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString("en-EU", { day: "2-digit", month: "short" });
}

export function shortAddress(
  address?: string | null,
  neighbourhood?: string | null,
  city?: string | null
) {
  if (address && neighbourhood) return `${address} · ${neighbourhood}`;
  return address || neighbourhood || city || "—";
}
