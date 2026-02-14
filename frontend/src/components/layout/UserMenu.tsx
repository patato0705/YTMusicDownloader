// src/components/layout/UserMenu.tsx
import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { LanguageSelector } from '../ui/LanguageSelector';

// Define Locale type to match i18n
type Locale = 'en' | 'fr';

export const UserMenu: React.FC<{
  onThemeToggle?: () => void;
  onLanguageToggle?: (locale: Locale) => void;
  currentTheme?: string;
  currentLocale?: Locale;
}> = ({ onThemeToggle, onLanguageToggle, currentTheme, currentLocale }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, right: 0 });
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

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
      const target = event.target as Node;
      const targetElement = target as Element;
      
      // Check if click is inside a language dropdown
      const isLanguageDropdown = targetElement.closest ? targetElement.closest('[data-language-dropdown="true"]') : null;
      
      if (
        menuRef.current && 
        !menuRef.current.contains(target) &&
        buttonRef.current &&
        !buttonRef.current.contains(target) &&
        !isLanguageDropdown
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const updateDropdownPosition = () => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + 12,
        right: window.innerWidth - rect.right
      });
    }
  };

  const handleToggle = () => {
    if (!isOpen) {
      updateDropdownPosition();
    }
    setIsOpen(!isOpen);
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  if (!user) return null;

  const roleColors: Record<string, string> = {
    administrator: 'bg-purple-500/20 text-purple-600 dark:text-purple-400 border-purple-500/50',
    member: 'bg-blue-500/20 text-blue-600 dark:text-blue-400 border-blue-500/50',
    visitor: 'bg-slate-500/20 text-slate-600 dark:text-slate-400 border-slate-500/50',
  };

  const roleGradients: Record<string, string> = {
    administrator: 'from-purple-500 to-pink-600',
    member: 'from-blue-500 to-indigo-600',
    visitor: 'from-slate-500 to-slate-600',
  };

  return (
    <>
      <button
        ref={buttonRef}
        onClick={handleToggle}
        className="flex items-center space-x-3 px-3 py-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-300 group"
      >
        <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${roleGradients[user.role]} flex items-center justify-center text-white font-semibold shadow-lg group-hover:scale-110 transition-transform`}>
          {user.username[0].toUpperCase()}
        </div>
        <div className="hidden sm:block text-left">
          <div className="text-sm font-medium text-slate-700 dark:text-zinc-200">{user.username}</div>
          <div className="text-xs text-muted-foreground capitalize">{user.role}</div>
        </div>
        <svg
          className={`w-4 h-4 text-muted-foreground transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`}
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
          className="fixed w-80 glass rounded-2xl shadow-2xl py-3 z-50 animate-in fade-in slide-in-from-top-2 duration-200"
          style={{
            top: `${dropdownPosition.top}px`,
            right: `${dropdownPosition.right}px`
          }}
        >
          {/* User info */}
          <div className="px-4 py-3 border-b border-slate-200 dark:border-white/10">
            <div className="flex items-center gap-3">
              <div className={`w-14 h-14 rounded-full bg-gradient-to-br ${roleGradients[user.role]} flex items-center justify-center text-white font-bold text-xl shadow-lg flex-shrink-0`}>
                {user.username[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <div className="font-semibold text-foreground truncate">{user.username}</div>
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full ${roleColors[user.role]} flex-shrink-0`}>
                    <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                    {user.role}
                  </span>
                </div>
                <div className="text-sm text-muted-foreground truncate">{user.email}</div>
              </div>
            </div>
          </div>

          {/* Menu items */}
          <div className="py-2">
            {/* Theme and Language - Mobile only */}
            {onThemeToggle && onLanguageToggle && (
              <div className="md:hidden px-4 py-3 border-b border-slate-200 dark:border-white/10 mb-2">
                <div className="flex items-center gap-3">
                  {/* Theme toggle */}
                  <button
                    onClick={onThemeToggle}
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/20 transition-all text-slate-700 dark:text-zinc-200"
                  >
                    {currentTheme === 'dark' ? (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                        </svg>
                        <span className="text-sm font-medium">Light</span>
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                        </svg>
                        <span className="text-sm font-medium">Dark</span>
                      </>
                    )}
                  </button>

                  {/* Language selector */}
                  <LanguageSelector
                    currentLocale={currentLocale || 'en'}
                    onLanguageChange={onLanguageToggle}
                    variant="mobile"
                  />
                </div>
              </div>
            )}
            
            <button
              onClick={() => {
                navigate('/settings');
                setIsOpen(false);
              }}
              className="w-full text-left px-4 py-2.5 text-sm text-foreground hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-200 flex items-center space-x-3 group"
            >
              <div className="w-8 h-8 rounded-lg bg-slate-100 dark:bg-white/10 flex items-center justify-center group-hover:bg-blue-500 dark:group-hover:bg-red-600 transition-colors">
                <svg className="w-4 h-4 text-slate-600 dark:text-zinc-400 group-hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <span className="font-medium">{t('nav.settings')}</span>
            </button>

            <button
              onClick={() => {
                navigate('/change-password');
                setIsOpen(false);
              }}
              className="w-full text-left px-4 py-2.5 text-sm text-foreground hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-200 flex items-center space-x-3 group"
            >
              <div className="w-8 h-8 rounded-lg bg-slate-100 dark:bg-white/10 flex items-center justify-center group-hover:bg-blue-500 dark:group-hover:bg-red-600 transition-colors">
                <svg className="w-4 h-4 text-slate-600 dark:text-zinc-400 group-hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
              </div>
              <span className="font-medium">{t('auth.changePassword.title')}</span>
            </button>

            {user.role === 'administrator' && (
              <button
                onClick={() => {
                  navigate('/admin');
                  setIsOpen(false);
                }}
                className="w-full text-left px-4 py-2.5 text-sm text-foreground hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-200 flex items-center space-x-3 group"
              >
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center shadow-lg">
                  <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                  </svg>
                </div>
                <span className="font-medium">{t('nav.admin')}</span>
              </button>
            )}

            <div className="border-t border-slate-200 dark:border-white/10 my-2"></div>

            <button
              onClick={handleLogout}
              className="w-full text-left px-4 py-2.5 text-sm text-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-all duration-200 flex items-center space-x-3 group"
            >
              <div className="w-8 h-8 rounded-lg bg-slate-100 dark:bg-white/10 flex items-center justify-center group-hover:bg-red-600 transition-colors">
                <svg className="w-4 h-4 text-slate-600 dark:text-zinc-400 group-hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
              </div>
              <span className="font-medium">{t('auth.logout')}</span>
            </button>
          </div>
        </div>,
        document.body
      )}
    </>
  );
};