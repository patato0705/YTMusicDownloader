// src/utils/formatting.ts

/**
 * A number with the locale's thousand separators
 */
export function formatNumber(num: number, locale: string): string {
  return num.toLocaleString(locale);
}
