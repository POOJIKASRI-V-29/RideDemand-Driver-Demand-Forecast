/** Presentation helpers. No prediction logic lives here — only formatting. */
import type { DemandLevel } from "../types/demand";

export const LEVEL_COLOR: Record<DemandLevel, string> = {
  very_high: "oklch(0.60 0.19 27)",
  high: "oklch(0.70 0.16 58)",
  moderate: "oklch(0.80 0.14 92)",
  low: "oklch(0.68 0.14 148)",
};

export const LEVEL_LABEL: Record<DemandLevel, string> = {
  very_high: "Very high demand",
  high: "High demand",
  moderate: "Moderate demand",
  low: "Low demand",
};

/** 19 -> "7:00 PM" */
export function formatHour(hour: number): string {
  const suffix = hour >= 12 ? "PM" : "AM";
  return `${hour % 12 || 12}:00 ${suffix}`;
}

/** 19 -> "7–8 PM" */
export function formatHourRange(hour: number): string {
  const end = (hour + 1) % 24;
  const startSuffix = hour >= 12 ? "PM" : "AM";
  const endSuffix = end >= 12 ? "PM" : "AM";
  const start = hour % 12 || 12;
  const finish = end % 12 || 12;
  return startSuffix === endSuffix
    ? `${start}–${finish} ${endSuffix}`
    : `${start} ${startSuffix} – ${finish} ${endSuffix}`;
}

/** Trims trailing zeros: 109.5 -> "109.5", 109.0 -> "109" */
export function formatDemand(value: number): string {
  return Number(value.toFixed(1)).toLocaleString("en-US");
}

/**
 * Error metrics need more precision than demand figures: the model and the
 * baseline differ in the second decimal place, and rounding to one would show
 * them as the same number.
 */
export function formatMetric(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(3);
}

export function formatCount(value: number | null | undefined): string {
  return value == null ? "—" : value.toLocaleString("en-US");
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
}
