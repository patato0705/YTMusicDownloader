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
import { Icon } from '../ui/icons';
import type { IconName } from '../ui/icons';


export function Navbar(): JSX.Element {
  const { isAuthenticated } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { formatLocale, t, tOr } = useI18n();
  const { features } = useFeatures();
  const { activeJobCount, activeByType, downloadsPausedUntil } = useJobActivity();
  const location = useLocation();
  const [scrolled, setScrolled] = useState(false);

  const navLinks: { to: string; label: string; icon: IconName }[] = [
    { to: '/', label: t('nav.home'), icon: 'home' },
    { to: '/browse', label: t('nav.browse'), icon: 'search' },
    { to: '/library', label: t('nav.library'), icon: 'library' },
    ...(features?.charts_enabled ? [{ to: '/charts', label: t('nav.charts'), icon: 'chart' as const }] : []),
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
      ? `${base} bg-accent-600 text-white shadow-lg`
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
                {/* Left: logo, links (md and up; phones get the tab bar below) */}
                <div className="flex items-center gap-2 sm:gap-4 min-w-0">
                  <Link to="/" className="flex items-center space-x-2 group min-w-0">
                    <Icon name="music" className="shrink-0 w-6 h-6 text-accent-600 dark:text-accent-400 transform group-hover:scale-110 transition-transform" />
                    <span className="text-sm sm:text-lg lg:text-xl font-bold text-accent-600 dark:text-accent-400 truncate">
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
                      <Icon name="refresh" strokeWidth={2.5} className="w-3.5 h-3.5 animate-spin" />
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
                    <Icon name={theme === 'dark' ? 'sun' : 'moon'} className="w-5 h-5 text-slate-700 dark:text-zinc-300 group-hover:text-accent-600 dark:group-hover:text-accent-400 transition-colors" />
                  </button>

                  <LanguageSelector variant="navbar" />

                  {isAuthenticated && <UserMenu />}
                </div>
              </div>

            </div>
          </div>
        </div>
      </nav>

      {/* Phones: the destinations stay one tap away at the bottom (App pads main to clear it) */}
      {isAuthenticated && (
        <nav
          aria-label={t('nav.main')}
          className="md:hidden fixed inset-x-0 bottom-0 z-50 glass !border-x-0 !border-b-0 pb-[env(safe-area-inset-bottom)]"
        >
          <div className="flex h-[var(--tab-bar-height)]">
            {navLinks.map((link) => {
              const active = location.pathname === link.to;
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  aria-current={active ? 'page' : undefined}
                  className={`flex-1 flex flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors outline-none focus-visible:bg-accent-500/10 ${
                    active ? 'text-accent-600 dark:text-accent-400' : 'text-slate-500 dark:text-zinc-400'
                  }`}
                >
                  <span className={`flex items-center justify-center w-14 h-7 rounded-full transition-colors ${active ? 'bg-accent-500/15' : ''}`}>
                    <Icon name={link.icon} className="w-5 h-5" />
                  </span>
                  {link.label}
                </Link>
              );
            })}
          </div>
        </nav>
      )}
    </>
  );
}
