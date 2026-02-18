// src/config/i18n.ts
/**
 * Centralized i18n configuration
 * To add a new language:
 * 1. Add it to SUPPORTED_LOCALES array
 * 2. Create the translation file in src/locales/{code}.json
 * That's it!
 */

export interface Language {
  code: string;
  name: string;
  flag: string;
}

export const SUPPORTED_LOCALES = [
  { code: 'en', name: 'English', flag: '🇬🇧' },
  { code: 'fr', name: 'Français', flag: '🇫🇷' },
  // Easy to add more:
  // { code: 'es', name: 'Español', flag: '🇪🇸' },
  // { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
  // { code: 'ja', name: '日本語', flag: '🇯🇵' },
] as const;

// Extract locale codes for type safety
export type Locale = typeof SUPPORTED_LOCALES[number]['code'];

// Default locale
export const DEFAULT_LOCALE: Locale = 'en';

// Helper to check if a string is a valid locale
export function isValidLocale(locale: string): locale is Locale {
  return SUPPORTED_LOCALES.some(l => l.code === locale);
}

// Get language by code
export function getLanguage(code: string): Language | undefined {
  return SUPPORTED_LOCALES.find(l => l.code === code);
}