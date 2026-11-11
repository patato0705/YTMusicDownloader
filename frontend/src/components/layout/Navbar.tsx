// src/components/layout/Navbar.tsx
import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { useFeatures } from '../../contexts/FeaturesContext';
import { useJobActivity } from '../../contexts/JobActivityContext';
import { UserMenu } from './UserMenu';
import { AppearanceMenu } from './AppearanceMenu';
import { LanguageSelector } from '../ui/LanguageSelector';
import { JobsBadge, RateLimitBadge } from './StatusBadges';
import { Icon } from '../ui/icons';
import type { IconName } from '../ui/icons';

export function Navbar(): JSX.Element {
  const { isAuthenticated } = useAuth();
  const { t } = useI18n();
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

  return (
    <>
      {/* Keeps the page clear of the floating navbar */}
      <div className="h-20" />

      <nav className={`fixed left-4 right-4 z-50 transition-all duration-300 ${scrolled ? 'top-2' : 'top-4'}`}>
        <div className="max-w-[1600px] mx-auto">
          <div
            className={`glass-chrome rounded-2xl shadow-xl transition-all duration-300 ${
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

                {/* Right: status badges, appearance and language (md and up), user menu */}
                <div className="flex items-center shrink-0 space-x-1 lg:space-x-2">
                  {isAuthenticated && downloadsPausedUntil && <RateLimitBadge until={downloadsPausedUntil} />}
                  {isAuthenticated && activeJobCount > 0 && <JobsBadge count={activeJobCount} byType={activeByType} />}

                  <AppearanceMenu />

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
          className="md:hidden fixed inset-x-0 bottom-0 z-50 glass-chrome !border-x-0 !border-b-0 pb-[env(safe-area-inset-bottom)]"
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
