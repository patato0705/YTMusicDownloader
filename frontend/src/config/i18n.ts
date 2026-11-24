// src/config/i18n.ts
/**
 * Supported languages. To add one: add it to SUPPORTED_LOCALES and create
 * its translation file, src/locales/{code}.json.
 */

export interface Language {
  code: string;
  name: string;
  flag: string;
}

export const SUPPORTED_LOCALES = [
  { code: 'en', name: 'English', flag: '🇬🇧' },
  { code: 'fr', name: 'Français', flag: '🇫🇷' },
] as const;

// Extract locale codes for type safety
export type Locale = typeof SUPPORTED_LOCALES[number]['code'];

// Default locale
export const DEFAULT_LOCALE: Locale = 'en';

// Helper to check if a string is a valid locale
export function isValidLocale(locale: string): locale is Locale {
  return SUPPORTED_LOCALES.some(l => l.code === locale);
}

/**
 * Locale for formatting dates and times: the browser's regional variant of the
 * UI language when it has one (en-GB, fr-CA...), so an English UI on a British
 * browser still gets a 24-hour clock. Falls back to the bare UI language,
 * whose defaults apply (fr: 24-hour, en: 12-hour).
 */
export function regionalLocale(locale: Locale): string {
  const regional = navigator.languages?.find(tag => tag.split('-')[0] === locale && tag.includes('-'));
  return regional ?? locale;
}

// Get language by code
export function getLanguage(code: string): Language | undefined {
  return SUPPORTED_LOCALES.find(l => l.code === code);
}