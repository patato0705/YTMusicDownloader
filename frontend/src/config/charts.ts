// src/config/charts.ts
/**
 * Countries whose YouTube Music chart can be followed: the major music
 * markets. Names come from the browser in the UI language (useCountryName).
 */
import { useMemo } from 'react';
import { useI18n } from '../contexts/I18nContext';

/** Most artists a chart subscription can follow (mirrors the backend limit). */
export const CHART_MAX_ARTISTS = 40;

export interface ChartCountry {
  /** ISO 3166-1 alpha-2 */
  code: string;
  flag: string;
}

export const CHART_COUNTRIES: ChartCountry[] = [
  // North America
  { code: 'US', flag: '🇺🇸' },
  { code: 'CA', flag: '🇨🇦' },
  { code: 'MX', flag: '🇲🇽' },
  
  // Europe
  { code: 'GB', flag: '🇬🇧' },
  { code: 'FR', flag: '🇫🇷' },
  { code: 'DE', flag: '🇩🇪' },
  { code: 'ES', flag: '🇪🇸' },
  { code: 'IT', flag: '🇮🇹' },
  { code: 'NL', flag: '🇳🇱' },
  { code: 'SE', flag: '🇸🇪' },
  { code: 'NO', flag: '🇳🇴' },
  { code: 'DK', flag: '🇩🇰' },
  { code: 'FI', flag: '🇫🇮' },
  { code: 'PL', flag: '🇵🇱' },
  { code: 'PT', flag: '🇵🇹' },
  { code: 'BE', flag: '🇧🇪' },
  { code: 'CH', flag: '🇨🇭' },
  { code: 'AT', flag: '🇦🇹' },
  { code: 'IE', flag: '🇮🇪' },
  
  // Asia-Pacific
  { code: 'JP', flag: '🇯🇵' },
  { code: 'KR', flag: '🇰🇷' },
  { code: 'AU', flag: '🇦🇺' },
  { code: 'NZ', flag: '🇳🇿' },
  { code: 'IN', flag: '🇮🇳' },
  { code: 'SG', flag: '🇸🇬' },
  { code: 'HK', flag: '🇭🇰' },
  { code: 'TW', flag: '🇹🇼' },
  { code: 'TH', flag: '🇹🇭' },
  { code: 'ID', flag: '🇮🇩' },
  { code: 'MY', flag: '🇲🇾' },
  { code: 'PH', flag: '🇵🇭' },
  { code: 'VN', flag: '🇻🇳' },
  
  // Latin America
  { code: 'BR', flag: '🇧🇷' },
  { code: 'AR', flag: '🇦🇷' },
  { code: 'CL', flag: '🇨🇱' },
  { code: 'CO', flag: '🇨🇴' },
  { code: 'PE', flag: '🇵🇪' },
  
  // Middle East and Africa
  { code: 'ZA', flag: '🇿🇦' },
  { code: 'AE', flag: '🇦🇪' },
  { code: 'SA', flag: '🇸🇦' },
  { code: 'TR', flag: '🇹🇷' },
  { code: 'IL', flag: '🇮🇱' },
  { code: 'EG', flag: '🇪🇬' },
  
  // Eastern Europe and Russia
  { code: 'RU', flag: '🇷🇺' },
  { code: 'UA', flag: '🇺🇦' },
  { code: 'CZ', flag: '🇨🇿' },
  { code: 'RO', flag: '🇷🇴' },
  { code: 'GR', flag: '🇬🇷' },
];

/**
 * Get country by code
 */
export function getCountry(code: string): ChartCountry | undefined {
  return CHART_COUNTRIES.find(c => c.code === code);
}

/** A country's name in the UI language, from its code */
export function useCountryName(): (code: string) => string {
  const { locale } = useI18n();
  const names = useMemo(() => new Intl.DisplayNames([locale], { type: 'region' }), [locale]);
  return (code: string) => names.of(code) ?? code;
}
