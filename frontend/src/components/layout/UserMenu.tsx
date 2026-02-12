// src/components/layout/UserMenu.tsx
import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';

export const UserMenu: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

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
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
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

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 glass rounded-2xl shadow-2xl border-slate-200 dark:border-white/10 py-3 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
          {/* User info */}
          <div className="px-4 py-3 border-b border-slate-200 dark:border-white/10">
            <div className="flex items-center space-x-3 mb-3">
              <div className={`w-14 h-14 rounded-full bg-gradient-to-br ${roleGradients[user.role]} flex items-center justify-center text-white font-bold text-xl shadow-lg`}>
                {user.username[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-foreground truncate">{user.username}</div>
                <div className="text-sm text-muted-foreground truncate">{user.email}</div>
              </div>
            </div>
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border ${roleColors[user.role]}`}>
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
              {user.role}
            </span>
          </div>

          {/* Menu items */}
          <div className="py-2">
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
              className="w-full text-left px-4 py-2.5 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-all duration-200 flex items-center space-x-3 group rounded-lg mx-2"
            >
              <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-950/50 flex items-center justify-center group-hover:bg-red-600 transition-colors">
                <svg className="w-4 h-4 text-red-600 dark:text-red-400 group-hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
              </div>
              <span className="font-medium">{t('auth.logout')}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};