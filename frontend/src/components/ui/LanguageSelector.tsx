// src/components/ui/LanguageSelector.tsx
import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';

// Define the Locale type to match what i18n expects
type Locale = 'en' | 'fr';

interface Language {
  code: Locale;
  name: string;
  flag: string;
}

const AVAILABLE_LANGUAGES: Language[] = [
  { code: 'en', name: 'English', flag: '🇬🇧' },
  { code: 'fr', name: 'Français', flag: '🇫🇷' },
  // Easy to add more - just update the Locale type above too:
  // { code: 'es', name: 'Español', flag: '🇪🇸' },
  // { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
  // { code: 'ja', name: '日本語', flag: '🇯🇵' },
];

interface LanguageSelectorProps {
  currentLocale: Locale;
  onLanguageChange: (locale: Locale) => void;
  variant?: 'navbar' | 'mobile';
  onOpenChange?: (isOpen: boolean) => void;
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  currentLocale,
  onLanguageChange,
  variant = 'navbar',
  onOpenChange,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0, right: 0 });
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const currentLanguage = AVAILABLE_LANGUAGES.find(lang => lang.code === currentLocale) || AVAILABLE_LANGUAGES[0];

  // Handle scroll to update dropdown position
  useEffect(() => {
    if (!isOpen) return;

    const handleScroll = () => {
      updateDropdownPosition();
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, [isOpen]);

  // Handle click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        menuRef.current && 
        !menuRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        onOpenChange?.(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onOpenChange]);

  const updateDropdownPosition = () => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + 20,
        left: rect.left,
        right: window.innerWidth - rect.right
      });
    }
  };

  const handleToggle = () => {
    const newState = !isOpen;
    if (newState) {
      updateDropdownPosition();
    }
    setIsOpen(newState);
    onOpenChange?.(newState);
  };

  const handleSelect = (code: Locale) => {
    onLanguageChange(code);
    setIsOpen(false);
    onOpenChange?.(false);
  };

  // Navbar variant (desktop)
  if (variant === 'navbar') {
    return (
      <>
        <button
          ref={buttonRef}
          onClick={handleToggle}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-white/10 hover:text-blue-600 dark:hover:text-red-400 transition-all duration-300"
          title="Change language"
        >
          <span>{currentLanguage.flag}</span>
          <span>{currentLanguage.code.toUpperCase()}</span>
          <svg
            className={`w-4 h-4 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {isOpen && createPortal(
          <div 
            ref={menuRef}
            className="fixed w-48 glass rounded-xl shadow-xl py-2 z-50"
            style={{ 
              top: `${dropdownPosition.top}px`, 
              right: `${dropdownPosition.right}px` 
            }}
          >
            {AVAILABLE_LANGUAGES.map((language) => (
              <button
                key={language.code}
                onClick={() => handleSelect(language.code)}
                className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center gap-3 ${
                  language.code === currentLocale
                    ? 'bg-blue-600 dark:bg-red-600 text-white font-medium'
                    : 'text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-white/10'
                }`}
              >
                <span className="text-lg">{language.flag}</span>
                <span>{language.name}</span>
                {language.code === currentLocale && (
                  <span className="ml-auto">✓</span>
                )}
              </button>
            ))}
          </div>,
          document.body
        )}
      </>
    );
  }

  // Mobile variant (for UserMenu)
  return (
    <>
      <button
        ref={buttonRef}
        onClick={handleToggle}
        className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/20 transition-all text-slate-700 dark:text-zinc-300"
      >
        <span>{currentLanguage.flag}</span>
        <span className="text-sm font-medium">{currentLanguage.code.toUpperCase()}</span>
        <svg
          className={`w-4 h-4 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && createPortal(
        <div 
          ref={menuRef}
          data-language-dropdown="true"
          className="fixed w-48 glass rounded-xl shadow-xl py-2 z-[60]"
          style={{ 
            top: `${dropdownPosition.top}px`, 
            left: `${dropdownPosition.left}px`
          }}
        >
          {AVAILABLE_LANGUAGES.map((language) => (
            <button
              key={language.code}
              onClick={() => handleSelect(language.code)}
              className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center gap-3 ${
                language.code === currentLocale
                  ? 'bg-blue-600 dark:bg-red-600 text-white font-medium'
                  : 'text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-white/10'
              }`}
            >
              <span className="text-lg">{language.flag}</span>
              <span>{language.name}</span>
              {language.code === currentLocale && (
                <span className="ml-auto">✓</span>
              )}
            </button>
          ))}
        </div>,
        document.body
      )}
    </>
  );
};