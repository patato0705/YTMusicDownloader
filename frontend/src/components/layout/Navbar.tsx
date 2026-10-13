// src/components/layout/Navbar.tsx
import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';
import { useI18n } from '../../contexts/I18nContext';
import { useFeatures } from '../../contexts/FeaturesContext';
import { useJobActivity } from '../../contexts/JobActivityContext';
import { UserMenu } from './UserMenu';
import { LanguageSelector } from '../ui/LanguageSelector';
import { InfoTooltip } from '../ui/InfoTooltip';

const SUN_PATH = 'M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z';
const MOON_PATH = 'M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z';

export function Navbar(): JSX.Element {
  const { isAuthenticated } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { formatLocale, t, tOr } = useI18n();
  const { features } = useFeatures();
  const { activeJobCount, activeByType, downloadsPausedUntil } = useJobActivity();
  const location = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = [
    { to: '/', label: t('nav.home') },
    { to: '/browse', label: t('nav.browse') },
    { to: '/library', label: t('nav.library') },
    ...(features?.charts_enabled ? [{ to: '/charts', label: t('nav.charts') }] : []),
  ];

  // The badge counts every kind of job, so a finished album can keep it lit
  // while its per-track lyrics fetches drain. Spell out what's actually running.
  const jobBreakdown = Object.entries(activeByType)
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a);

  const jobSummary = t('nav.activeJobs', { count: activeJobCount });

  const jobTooltip = (
    <>
      <div className="font-medium">{jobSummary}</div>
      {jobBreakdown.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-muted-foreground">
          {jobBreakdown.map(([type, count]) => (
            <li key={type} className="flex justify-between gap-6">
              <span>{tOr(`nav.jobTypes.${type}`, type.replace(/_/g, ' '))}</span>
              <span className="tabular-nums">{count}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );

  const pausedTooltip = downloadsPausedUntil
    ? t('nav.rateLimited', {
        time: new Date(downloadsPausedUntil).toLocaleTimeString(formatLocale, { hour: '2-digit', minute: '2-digit' }),
      })
    : '';

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navLinkClass = (path: string) => {
    const base = 'px-3 lg:px-4 py-2 rounded-xl text-sm font-medium transition-all duration-300';
    return location.pathname === path
      ? `${base} bg-blue-600 dark:bg-red-600 text-white shadow-lg`
      : `${base} text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-white/10`;
  };

  const themeLabel = theme === 'dark' ? t('settings.theme.switchToLight') : t('settings.theme.switchToDark');

  return (
    <>
      {/* Keeps the page clear of the floating navbar */}
      <div className="h-20" />

      <nav className={`fixed left-4 right-4 z-50 transition-all duration-300 ${scrolled ? 'top-2' : 'top-4'}`}>
        <div className="max-w-[1600px] mx-auto">
          <div
            className={`glass border-slate-200 dark:border-white/10 rounded-2xl shadow-xl transition-all duration-300 ${
              scrolled ? 'shadow-2xl' : ''
            }`}
          >
            <div className="px-4 sm:px-6">
              <div className="flex items-center justify-between h-16">
                {/* Left: menu button (phones), logo, links (md and up) */}
                <div className="flex items-center gap-2 sm:gap-4 min-w-0">
                  {isAuthenticated && (
                    <button
                      type="button"
                      onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                      className="md:hidden shrink-0 p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-300"
                      aria-label={t('nav.toggleMenu')}
                      aria-expanded={mobileMenuOpen}
                    >
                      <svg className="w-6 h-6 text-slate-700 dark:text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d={mobileMenuOpen ? 'M6 18L18 6M6 6l12 12' : 'M4 6h16M4 12h16M4 18h16'}
                        />
                      </svg>
                    </button>
                  )}

                  <Link to="/" className="flex items-center space-x-2 group min-w-0">
                    <div className="shrink-0 text-2xl transform group-hover:scale-110 transition-transform" aria-hidden="true">🎵</div>
                    <span className="text-sm sm:text-lg lg:text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-red-500 dark:to-red-700 truncate">
                      YTMusicDownloader
                    </span>
                  </Link>

                  {isAuthenticated && (
                    <div className="hidden md:flex shrink-0 space-x-1 ml-2 lg:ml-6">
                      {navLinks.map((link) => (
                        <Link key={link.to} to={link.to} className={navLinkClass(link.to)}>
                          {link.label}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>

                {/* Right: status badges, theme and language (md and up), user menu */}
                <div className="flex items-center shrink-0 space-x-1 lg:space-x-2">
                  {/* YouTube rate limit: downloads paused (backend/jobs/gate.py) */}
                  {isAuthenticated && downloadsPausedUntil && (
                    <InfoTooltip
                      label={pausedTooltip}
                      content={pausedTooltip}
                      className="flex items-center justify-center w-7 h-7 rounded-xl bg-red-500/15 text-red-600 dark:text-red-400 text-sm font-bold"
                    >
                      !
                    </InfoTooltip>
                  )}

                  {isAuthenticated && activeJobCount > 0 && (
                    <InfoTooltip
                      label={jobSummary}
                      content={jobTooltip}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-amber-500/15 text-amber-600 dark:text-amber-400 text-xs font-medium"
                    >
                      <svg className="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      <span className="tabular-nums">{activeJobCount}</span>
                    </InfoTooltip>
                  )}

                  <button
                    type="button"
                    onClick={toggleTheme}
                    className="hidden md:block p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-300 group"
                    aria-label={themeLabel}
                    title={themeLabel}
                  >
                    <svg className="w-5 h-5 text-slate-700 dark:text-zinc-300 group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={theme === 'dark' ? SUN_PATH : MOON_PATH} />
                    </svg>
                  </button>

                  <LanguageSelector variant="navbar" />

                  {isAuthenticated && <UserMenu />}
                </div>
              </div>

              {isAuthenticated && mobileMenuOpen && (
                <div className="md:hidden border-t border-slate-200 dark:border-white/10 py-3 space-y-1">
                  {navLinks.map((link) => (
                    <Link
                      key={link.to}
                      to={link.to}
                      className={navLinkClass(link.to)}
                      onClick={() => setMobileMenuOpen(false)}
                    >
                      {link.label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </nav>
    </>
  );
}
