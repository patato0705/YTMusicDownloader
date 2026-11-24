// src/utils/formatting.ts

/**
 * A number with the locale's thousand separators
 */
export function formatNumber(num: number, locale: string): string {
  return num.toLocaleString(locale);
}

/**
 * Items as one list in the locale's words: "a, b, and c", "a, b et c",
 * "a、b、c" (Japanese), "a وb وc" (Arabic)
 */
export function formatList(items: string[], locale: string): string {
  return new Intl.ListFormat(locale, { type: 'conjunction' }).format(items);
}
