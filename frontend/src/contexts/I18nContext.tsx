// src/contexts/I18nContext.tsx
import React, { createContext, useCallback, useContext, useState, useEffect, useMemo } from 'react';
import { Locale, DEFAULT_LOCALE, isValidLocale, regionalLocale } from '../config/i18n';
import { readStorage, writeStorage } from '../utils/storage';
import { translate, type Params, type Translations } from '../utils/translate';

interface I18nContextType {
  locale: Locale;
  /** Pass to Intl/toLocale* for dates and times (see regionalLocale). */
  formatLocale: string;
  setLocale: (locale: Locale) => void;
  /**
   * Translate a key, replacing {param}s. With a numeric `count` param, the
   * key's variant for the language's plural form of that count is used when
   * it exists ("_one", "_few"...: see utils/translate).
   */
  t: (key: string, params?: Params) => string;
  /** t(), or `fallback` when the key has no translation (e.g. labels defined by the backend) */
  tOr: (key: string, fallback: string, params?: Params) => string;
}

const I18nContext = createContext<I18nContextType | undefined>(undefined);

const translationCache: Partial<Record<Locale, Translations>> = {};

async function loadTranslations(locale: Locale): Promise<Translations> {
  const cached = translationCache[locale];
  if (cached) return cached;

  try {
    const module = await import(`../locales/${locale}.json`);
    translationCache[locale] = module.default;
    return module.default;
  } catch (error) {
    console.error(`Failed to load translations for ${locale}:`, error);
    return {};
  }
}

function initialLocale(): Locale {
  const stored = readStorage('locale');
  if (stored && isValidLocale(stored)) return stored;

  const browserLang = navigator.language.split('-')[0];
  if (isValidLocale(browserLang)) return browserLang;

  return DEFAULT_LOCALE;
}

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [locale, setLocale] = useState<Locale>(initialLocale);
  // null until the first locale has loaded; a later switch keeps the old
  // strings on screen until the new ones arrive
  const [translations, setTranslations] = useState<Translations | null>(null);
  const formatLocale = useMemo(() => regionalLocale(locale), [locale]);
  const pluralRules = useMemo(() => new Intl.PluralRules(locale), [locale]);

  // Load translations when locale changes
  useEffect(() => {
    let current = true;
    loadTranslations(locale).then(loaded => {
      // A quick second switch must not be overwritten by the first's late load
      if (current) setTranslations(loaded);
    });
    writeStorage('locale', locale);
    document.documentElement.lang = locale;
    return () => { current = false; };
  }, [locale]);

  const tOr = useCallback(
    (key: string, fallback: string, params?: Params): string =>
      translate(translations ?? {}, pluralRules, key, params) ?? fallback,
    [translations, pluralRules],
  );

  // A missing translation shows its key, so it stands out
  const t = useCallback((key: string, params?: Params) => tOr(key, key, params), [tOr]);

  const value = useMemo(
    () => ({ locale, formatLocale, setLocale, t, tOr }),
    [locale, formatLocale, t, tOr],
  );

  // Nothing renders before the first strings load, or the app would race the
  // translation chunk and sometimes paint raw keys ("common.loading")
  return (
    <I18nContext.Provider value={value}>
      {translations && children}
    </I18nContext.Provider>
  );
};

export const useI18n = () => {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within I18nProvider');
  }
  return context;
};
