// src/components/Navbar.tsx
import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { useI18n } from '../contexts/I18nContext';
import { UserMenu } from './UserMenu';

export default function Navbar(): JSX.Element {
  const { isAuthenticated } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { locale, setLocale, t } = useI18n();
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname === path;
  };

  const navLinkClass = (path: string) => {
    const base = 'px-3 py-2 rounded-md text-sm font-medium transition-colors';
    return isActive(path)
      ? `${base} bg-primary text-primary-foreground`
      : `${base} text-foreground hover:bg-accent`;
  };

  const toggleLanguage = () => {
    setLocale(locale === 'en' ? 'fr' : 'en');
  };

  return (
    <nav className="bg-card border-b border-border shadow-sm">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo and main navigation */}
          <div className="flex items-center space-x-8">
            <Link to="/" className="flex items-center space-x-2">
              <div className="text-2xl">🎵</div>
              <span className="text-xl font-bold text-foreground">
                Music Library
              </span>
            </Link>

            {isAuthenticated && (
              <div className="hidden md:flex space-x-1">
                <Link to="/" className={navLinkClass('/')}>
                  {t('nav.home')}
                </Link>
                <Link to="/browse" className={navLinkClass('/browse')}>
                  {t('nav.browse')}
                </Link>
                <Link to="/library" className={navLinkClass('/library')}>
                  {t('nav.library')}
                </Link>
                <Link to="/settings" className={navLinkClass('/settings')}>
                  {t('nav.settings')}
                </Link>
              </div>
            )}
          </div>

          {/* Right side - Theme toggle, Language, User menu */}
          <div className="flex items-center space-x-2">
            {/* Theme toggle */}
            <button
              onClick={toggleTheme}
              className="p-2 rounded-md hover:bg-accent transition-colors"
              aria-label="Toggle theme"
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {theme === 'dark' ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              )}
            </button>

            {/* Language toggle */}
            <button
              onClick={toggleLanguage}
              className="px-3 py-2 rounded-md text-sm font-medium hover:bg-accent transition-colors"
              title="Change language"
            >
              {locale.toUpperCase()}
            </button>

            {/* User menu */}
            {isAuthenticated && <UserMenu />}
          </div>

          {/* Mobile menu button */}
          {isAuthenticated && (
            <div className="md:hidden">
              <button
                className="p-2 rounded-md hover:bg-accent transition-colors"
                aria-label="Open menu"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}