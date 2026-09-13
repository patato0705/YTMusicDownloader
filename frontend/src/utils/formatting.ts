// src/utils/formatting.ts

/**
 * Formats a number with thousand separators
 */
export function formatNumber(num: number | null | undefined): string {
  if (num === null || num === undefined) return '0';

  return num.toLocaleString('en-US');
}
