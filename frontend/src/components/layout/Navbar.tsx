// src/components/layout/Navbar.tsx
import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { useI18n } from '../../contexts/I18nContext';
import { UserMenu } from './UserMenu';
import { LanguageSelector } from '../ui/LanguageSelector';
import { getFeatures } from '../../api/features';
import { useJobActivity } from '../../contexts/JobActivityContext';

export default function Navbar(): JSX.Element {
  const { isAuthenticated } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { locale, setLocale, t } = useI18n();
  const location = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [chartsEnabled, setChartsEnabled] = useState(false);
  const { activeJobCount, activeByType } = useJobActivity();

  // Check if charts feature is enabled
  useEffect(() => {
    const checkChartsEnabled = async () => {
      try {
        const { charts_enabled } = await getFeatures();
        setChartsEnabled(charts_enabled);
      } catch (err) {
        console.error('Failed to check charts setting:', err);
        setChartsEnabled(false);
      }
    };
    
    if (isAuthenticated) {
      checkChartsEnabled();
    }
  }, [isAuthenticated]);

  // The badge counts every kind of job, so a finished album can keep it lit
  // while its per-track lyrics fetches drain. Spell out what's actually running.
  const jobTypeLabel = (type: string) => {
    const key = `nav.jobTypes.${type}`;
    const label = t(key);
    return label === key ? type.replace(/_/g, ' ') : label;
  };

  const jobBreakdown = Object.entries(activeByType)
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([type, count]) => `${jobTypeLabel(type)}: ${count}`)
    .join(' · ');

  const jobTooltip = [
    t('nav.activeJobs', { count: String(activeJobCount) }),
    jobBreakdown,
  ].filter(Boolean).join('\n');

  // Handle scroll effect
  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const isActive = (path: string) => {
    return location.pathname === path;
  };

  const navLinkClass = (path: string) => {
    const base = 'px-4 py-2 rounded-xl text-sm font-medium transition-all duration-300';
    return isActive(path)
      ? `${base} bg-blue-600 dark:bg-red-600 text-white shadow-lg`
      : `${base} text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-white/10`;
  };

  const toggleLanguage = () => {
    setLocale(locale === 'en' ? 'fr' : 'en');
  };

  return (
    <>
      {/* Spacer to prevent content jump */}
      <div className="h-20" />
      
      {/* Floating Navbar */}
      <nav 
        className={`fixed left-4 right-4 z-50 transition-all duration-300 ${
          scrolled ? 'top-2' : 'top-4'
        }`}
      >
        <div className="max-w-[1600px] mx-auto">
          <div 
            className={`glass border-slate-200 dark:border-white/10 rounded-2xl shadow-xl transition-all duration-300 ${
              scrolled ? 'shadow-2xl' : ''
            }`}
          >
            <div className="px-4 sm:px-6">
              <div className="flex items-center justify-between h-16">
                {/* Left side: Hamburger (mobile) + Logo + Nav (desktop) */}
                <div className="flex items-center gap-2 sm:gap-4">
                  {/* Mobile menu button - left side */}
                  {isAuthenticated && (
                    <button
                      onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                      className="md:hidden p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-300"
                      aria-label="Toggle menu"
                    >
                      <svg className="w-6 h-6 text-slate-700 dark:text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        {mobileMenuOpen ? (
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        ) : (
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                        )}
                      </svg>
                    </button>
                  )}

                  {/* Logo */}
                  <Link to="/" className="flex items-center space-x-2 group">
                    <div className="text-2xl transform group-hover:scale-110 transition-transform">🎵</div>
                    <span className="text-base sm:text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-red-500 dark:to-red-700 whitespace-nowrap">
                      Music Library
                    </span>
                  </Link>

                  {/* Desktop navigation */}
                  {isAuthenticated && (
                    <div className="hidden md:flex space-x-1 ml-6">
                      <Link to="/" className={navLinkClass('/')}>
                        {t('nav.home')}
                      </Link>
                      <Link to="/browse" className={navLinkClass('/browse')}>
                        {t('nav.browse')}
                      </Link>
                      <Link to="/library" className={navLinkClass('/library')}>
                        {t('nav.library')}
                      </Link>
                      {chartsEnabled && (
                        <Link to="/charts" className={navLinkClass('/charts')}>
                          {t('nav.charts')}
                        </Link>
                      )}
                    </div>
                  )}
                </div>

                {/* Right side - Desktop: Theme + Language + User, Mobile: User only */}
                <div className="flex items-center space-x-2">
                  {/* Active jobs indicator */}
                  {isAuthenticated && activeJobCount > 0 && (
                    <div
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-amber-500/15 text-amber-600 dark:text-amber-400 text-xs font-medium"
                      title={jobTooltip}
                    >
                      <svg className="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      <span className="tabular-nums">{activeJobCount}</span>
                    </div>
                  )}

                  {/* Theme toggle - Desktop only */}
                  <button
                    onClick={toggleTheme}
                    className="hidden md:block p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-300 group"
                    aria-label="Toggle theme"
                    title={theme === 'dark' ? t('settings.theme.switchToLight') : t('settings.theme.switchToDark')}
                  >
                    {theme === 'dark' ? (
                      <svg className="w-5 h-5 text-slate-700 dark:text-zinc-300 group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5 text-slate-700 dark:text-zinc-300 group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                      </svg>
                    )}
                  </button>

                  {/* Language selector - Desktop only */}
                  <LanguageSelector
                    currentLocale={locale}
                    onLanguageChange={setLocale}
                    variant="navbar"
                  />

                  {/* User menu - Pass theme and language toggles for mobile */}
                  {isAuthenticated && (
                    <UserMenu 
                      onThemeToggle={toggleTheme}
                      onLanguageToggle={setLocale}
                      currentTheme={theme}
                      currentLocale={locale}
                    />
                  )}
                </div>
              </div>

              {/* Mobile menu */}
              {isAuthenticated && mobileMenuOpen && (
                <div className="md:hidden border-t border-slate-200 dark:border-white/10 py-3 space-y-1">
                  <Link 
                    to="/" 
                    className={navLinkClass('/')}
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    {t('nav.home')}
                  </Link>
                  <Link 
                    to="/browse" 
                    className={navLinkClass('/browse')}
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    {t('nav.browse')}
                  </Link>
                  <Link 
                    to="/library" 
                    className={navLinkClass('/library')}
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    {t('nav.library')}
                  </Link>
                  {chartsEnabled && (
                    <Link
                      to="/charts"
                      className={navLinkClass('/charts')}
                      onClick={() => setMobileMenuOpen(false)}
                    >
                      {t('nav.charts')}
                    </Link>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </nav>
    </>
  );
}