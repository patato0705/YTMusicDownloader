// src/components/ui/LanguageSelector.tsx
import React from 'react';
import { createPortal } from 'react-dom';
import { SUPPORTED_LOCALES, getLanguage } from '../../config/i18n';
import { useI18n } from '../../contexts/I18nContext';
import { useDropdown } from '../../hooks/useDropdown';

interface LanguageSelectorProps {
  /** navbar: desktop navbar button; menu: full-width button inside the user menu (phones) */
  variant: 'navbar' | 'menu';
}

const BUTTON_CLASSES = {
  navbar: 'hidden md:flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-white/10 hover:text-accent-600 dark:hover:text-accent-400 transition-all duration-300',
  menu: 'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/20 transition-all text-sm font-medium text-slate-700 dark:text-zinc-300',
};

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({ variant }) => {
  const { locale, setLocale, t } = useI18n();
  const { open, setOpen, toggle, buttonRef, menuRef, menuStyle } = useDropdown(variant === 'navbar' ? 'right' : 'left', 20);
  const current = getLanguage(locale) ?? SUPPORTED_LOCALES[0];

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-label={t('settings.changeLanguage')}
        title={t('settings.changeLanguage')}
        className={BUTTON_CLASSES[variant]}
      >
        <span aria-hidden="true">{current.flag}</span>
        <span className={variant === 'navbar' ? 'hidden lg:inline' : ''}>{current.code.toUpperCase()}</span>
        <svg
          className={`w-4 h-4 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && createPortal(
        <div ref={menuRef} className="fixed w-48 glass rounded-xl shadow-xl py-2 z-[60]" style={menuStyle}>
          {SUPPORTED_LOCALES.map((language) => (
            <button
              key={language.code}
              type="button"
              onClick={() => {
                setLocale(language.code);
                setOpen(false);
              }}
              className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center gap-3 ${
                language.code === locale
                  ? 'bg-accent-600 text-white font-medium'
                  : 'text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-white/10'
              }`}
            >
              <span className="text-lg" aria-hidden="true">{language.flag}</span>
              <span>{language.name}</span>
              {language.code === locale && <span className="ml-auto">✓</span>}
            </button>
          ))}
        </div>,
        document.body
      )}
    </>
  );
};
