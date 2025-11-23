// src/contexts/I18nContext.tsx
import React, { createContext, useContext, useState, useEffect } from 'react';

type Locale = 'en' | 'fr';

type Translations = Record<string, any>;

interface I18nContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
  translations: Translations;
}

const I18nContext = createContext<I18nContextType | undefined>(undefined);

// Translation files will be imported dynamically
const translationCache: Record<Locale, Translations> = {} as any;

async function loadTranslations(locale: Locale): Promise<Translations> {
  if (translationCache[locale]) {
    return translationCache[locale];
  }

  try {
    const module = await import(`../locales/${locale}.json`);
    translationCache[locale] = module.default;
    return module.default;
  } catch (error) {
    console.error(`Failed to load translations for ${locale}:`, error);
    return {};
  }
}

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [locale, setLocaleState] = useState<Locale>(() => {
    // Check localStorage
    const stored = localStorage.getItem('locale') as Locale | null;
    if (stored && ['en', 'fr'].includes(stored)) {
      return stored;
    }

    // Check browser language
    const browserLang = navigator.language.split('-')[0];
    if (browserLang === 'fr') return 'fr';
    
    return 'en';
  });

  const [translations, setTranslations] = useState<Translations>({});

  // Load translations when locale changes
  useEffect(() => {
    loadTranslations(locale).then(setTranslations);
    localStorage.setItem('locale', locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale);
  };

  /**
   * Translate a key with optional parameter substitution
   * 
   * @example
   * t('welcome') // "Welcome"
   * t('greeting', { name: 'John' }) // "Hello, John!"
   */
  const t = (key: string, params?: Record<string, string | number>): string => {
    // Navigate nested keys (e.g., "auth.login.title")
    const keys = key.split('.');
    let value: any = translations;

    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k];
      } else {
        // Key not found, return the key itself as fallback
        return key;
      }
    }

    if (typeof value !== 'string') {
      return key;
    }

    // Replace parameters {param} with values
    if (params) {
      return value.replace(/\{(\w+)\}/g, (match, param) => {
        return param in params ? String(params[param]) : match;
      });
    }

    return value;
  };

  return (
    <I18nContext.Provider value={{ locale, setLocale, t, translations }}>
      {children}
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