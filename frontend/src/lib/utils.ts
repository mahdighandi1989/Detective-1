import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

/**
 * Merge Tailwind CSS classes with proper precedence handling.
 * Combines clsx (conditional classes) with tailwind-merge (conflict resolution).
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Risk level categories used across the Detective-1 platform.
 * Maps directly to the risk engine classification output.
 */
export type RiskLevel = "clean" | "suspicious" | "infiltrator" | "transformed" | "unknown"

/**
 * Persian (fa) display labels for each risk level.
 */
export const RISK_LEVEL_LABELS: Record<RiskLevel, string> = {
  clean: "پاک",
  suspicious: "مشکوک",
  infiltrator: "نفوذی",
  transformed: "استحاله‌یافته",
  unknown: "نامشخص",
}

/**
 * Tailwind/HEX color mapping for risk visualization (used in graph nodes,
 * badges, and charts). Green → low risk, red → high risk.
 */
export const RISK_LEVEL_COLORS: Record<RiskLevel, string> = {
  clean: "#22c55e",        // green-500
  suspicious: "#eab308",   // yellow-500
  infiltrator: "#ef4444",  // red-500
  transformed: "#f97316",  // orange-500
  unknown: "#6b7280",      // gray-500
}

/**
 * Tailwind utility class set for rendering risk-level badges.
 */
export const RISK_LEVEL_BADGE_CLASSES: Record<RiskLevel, string> = {
  clean: "bg-green-100 text-green-800 border-green-300",
  suspicious: "bg-yellow-100 text-yellow-800 border-yellow-300",
  infiltrator: "bg-red-100 text-red-800 border-red-300",
  transformed: "bg-orange-100 text-orange-800 border-orange-300",
  unknown: "bg-gray-100 text-gray-800 border-gray-300",
}

/**
 * Normalize an arbitrary string into a known RiskLevel.
 * Falls back to "unknown" for unrecognized values.
 */
export function normalizeRiskLevel(value: string | null | undefined): RiskLevel {
  if (!value) return "unknown"
  const v = value.toLowerCase().trim()
  if (v === "clean" || v === "پاک") return "clean"
  if (v === "suspicious" || v === "مشکوک") return "suspicious"
  if (v === "infiltrator" || v === "نفوذی") return "infiltrator"
  if (v === "transformed" || v === "استحاله‌یافته" || v === "استحاله") return "transformed"
  return "unknown"
}

/**
 * Return the localized (fa) label for a risk level value.
 */
export function getRiskLabel(value: string | null | undefined): string {
  return RISK_LEVEL_LABELS[normalizeRiskLevel(value)]
}

/**
 * Return the HEX color for a risk level value.
 */
export function getRiskColor(value: string | null | undefined): string {
  return RISK_LEVEL_COLORS[normalizeRiskLevel(value)]
}

/**
 * Return the badge utility classes for a risk level value.
 */
export function getRiskBadgeClasses(value: string | null | undefined): string {
  return RISK_LEVEL_BADGE_CLASSES[normalizeRiskLevel(value)]
}

/**
 * Clamp a numeric risk score (0-100) and map it to a RiskLevel.
 * Thresholds: 0-24 clean, 25-49 suspicious, 50-74 transformed, 75-100 infiltrator.
 */
export function riskScoreToLevel(score: number | null | undefined): RiskLevel {
  if (score == null || Number.isNaN(score)) return "unknown"
  const s = Math.max(0, Math.min(100, score))
  if (s < 25) return "clean"
  if (s < 50) return "suspicious"
  if (s < 75) return "transformed"
  return "infiltrator"
}

/**
 * Source credibility tiers used by the OSINT agent / source scoring.
 */
export type CredibilityTier = "high" | "medium" | "low" | "unverified"

/**
 * Map a numeric credibility score (0-100) to a credibility tier.
 */
export function credibilityScoreToTier(score: number | null | undefined): CredibilityTier {
  if (score == null || Number.isNaN(score)) return "unverified"
  const s = Math.max(0, Math.min(100, score))
  if (s >= 75) return "high"
  if (s >= 50) return "medium"
  if (s > 0) return "low"
  return "unverified"
}

/**
 * Persian display labels for credibility tiers.
 */
export const CREDIBILITY_TIER_LABELS: Record<CredibilityTier, string> = {
  high: "بالا",
  medium: "متوسط",
  low: "پایین",
  unverified: "تأییدنشده",
}

/**
 * Format a date value into a localized fa-IR string.
 * Accepts ISO strings, timestamps, or Date objects.
 */
export function formatDate(
  value: string | number | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  if (value == null) return "—"
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("fa-IR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    ...options,
  }).format(date)
}

/**
 * Format a date value with time included (fa-IR).
 */
export function formatDateTime(
  value: string | number | Date | null | undefined
): string {
  return formatDate(value, {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

/**
 * Return a relative time string (e.g. "۳ ساعت پیش") in fa-IR.
 */
export function formatRelativeTime(
  value: string | number | Date | null | undefined
): string {
  if (value == null) return "—"
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return "—"

  const diffMs = date.getTime() - Date.now()
  const rtf = new Intl.RelativeTimeFormat("fa-IR", { numeric: "auto" })

  const divisions: { amount: number; unit: Intl.RelativeTimeFormatUnit }[] = [
    { amount: 60, unit: "second" },
    { amount: 60, unit: "minute" },
    { amount: 24, unit: "hour" },
    { amount: 7, unit: "day" },
    { amount: 4.34524, unit: "week" },
    { amount: 12, unit: "month" },
    { amount: Number.POSITIVE_INFINITY, unit: "year" },
  ]

  let duration = diffMs / 1000
  for (const division of divisions) {
    if (Math.abs(duration) < division.amount) {
      return rtf.format(Math.round(duration), division.unit)
    }
    duration /= division.amount
  }
  return formatDate(date)
}

/**
 * Truncate a string to a max length, appending an ellipsis.
 */
export function truncate(text: string | null | undefined, maxLength = 120): string {
  if (!text) return ""
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength).trimEnd() + "…"
}

/**
 * Convert Western Arabic digits in a string to Persian digits.
 */
export function toPersianDigits(value: string | number): string {
  const persianDigits = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"]
  return String(value).replace(/\d/g, (d) => persianDigits[Number(d)])
}

/**
 * Convert Persian/Arabic digits in a string to Western Arabic digits.
 */
export function toEnglishDigits(value: string): string {
  return value
    .replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
}

/**
 * Build a slug from arbitrary text (supports Persian by preserving non-ASCII
 * word chars and collapsing whitespace/punctuation to hyphens).
 */
export function slugify(text: string): string {
  return text
    .toString()
    .trim()
    .toLowerCase()
    .replace(/[\s\u200c]+/g, "-")
    .replace(/[^\p{L}\p{N}-]+/gu, "")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "")
}

/**
 * Capitalize the first character of a string.
 */
export function capitalize(text: string | null | undefined): string {
  if (!text) return ""
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/**
 * Generate initials from a person's full name (up to 2 chars).
 */
export function getInitials(name: string | null | undefined): string {
  if (!name) return "?"
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return "?"
  if (parts.length === 1) return parts[0].slice(0, 2)
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

/**
 * Format a byte count into a human-readable size string.
 */
export function formatBytes(bytes: number, decimals = 1): string {
  if (!bytes || bytes <= 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`
}

/**
 * Debounce a function, delaying its execution until after `wait` ms have
 * elapsed since the last invocation.
 */
export function debounce<T extends (...args: never[]) => unknown>(
  fn: T,
  wait = 300
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(() => fn(...args), wait)
  }
}

/**
 * Safely parse JSON, returning a fallback on failure.
 */
export function safeJsonParse<T>(value: string | null | undefined, fallback: T): T {
  if (!value) return fallback
  try {
    return JSON.parse(value) as T
  } catch {
    return fallback
  }
}

/**
 * Sleep helper for async flows (e.g. retry backoff in API clients).
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Build a