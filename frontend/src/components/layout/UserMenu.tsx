// src/components/layout/UserMenu.tsx
import React from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { useTheme } from '../../contexts/ThemeContext';
import { useDropdown } from '../../hooks/useDropdown';
import { LanguageSelector } from '../ui/LanguageSelector';
import { ROLE_COLORS } from '../../config/roles';
import type { Role } from '../../api/auth';
import { Icon, ICON_PATHS } from '../ui/icons';

const ROLE_GRADIENTS: Record<Role, string> = {
  administrator: 'from-purple-500 to-pink-600',
  member: 'from-accent-500 to-accent-600',
  visitor: 'from-slate-500 to-slate-600',
};


interface MenuItemProps {
  icon: string;
  label: string;
  onClick: () => void;
  /** Tile behind the icon */
  iconClassName: string;
  className?: string;
}

const MenuItem: React.FC<MenuItemProps> = ({ icon, label, onClick, iconClassName, className = '' }) => (
  <button
    type="button"
    onClick={onClick}
    className={`w-full text-left px-4 py-2.5 text-sm text-foreground transition-all duration-200 flex items-center space-x-3 group ${className}`}
  >
    <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${iconClassName}`}>
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={icon} />
      </svg>
    </div>
    <span className="font-medium">{label}</span>
  </button>
);

export const UserMenu: React.FC = () => {
  const { open, setOpen, toggle, buttonRef, menuRef, menuStyle } = useDropdown('right', 12);
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { t } = useI18n();
  const navigate = useNavigate();

  if (!user) return null;

  const go = (path: string) => {
    navigate(path);
    setOpen(false);
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const roleName = t(`admin.users.roles.${user.role}`);
  const initial = user.username[0].toUpperCase();
  const plainItem = 'bg-slate-100 dark:bg-white/10 text-slate-600 dark:text-zinc-400 group-hover:text-white';

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex items-center space-x-3 px-3 py-2 rounded-xl hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-300 group"
      >
        <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${ROLE_GRADIENTS[user.role]} flex items-center justify-center text-white font-semibold shadow-lg group-hover:scale-110 transition-transform`}>
          {initial}
        </div>
        <div className="hidden sm:max-md:block lg:block text-left">
          <div className="text-sm font-medium text-slate-700 dark:text-zinc-200">{user.username}</div>
          <div className="text-xs text-muted-foreground">{roleName}</div>
        </div>
        <svg
          className={`w-4 h-4 text-muted-foreground transition-transform duration-300 ${open ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && createPortal(
        <div ref={menuRef} className="fixed w-80 glass rounded-2xl shadow-2xl py-3 z-50" style={menuStyle}>
          {/* User info */}
          <div className="px-4 py-3 border-b border-slate-200 dark:border-white/10">
            <div className="flex items-center gap-3">
              <div className={`w-14 h-14 rounded-full bg-gradient-to-br ${ROLE_GRADIENTS[user.role]} flex items-center justify-center text-white font-bold text-xl shadow-lg flex-shrink-0`}>
                {initial}
              </div>
              <div className="flex-1 min-w-0 flex items-center gap-2">
                <div className="font-semibold text-foreground truncate">{user.username}</div>
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full ${ROLE_COLORS[user.role]} flex-shrink-0`}>
                  <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                  {roleName}
                </span>
              </div>
            </div>
          </div>

          <div className="py-2">
            {/* Theme and language: in the navbar from md up */}
            <div className="md:hidden px-4 py-3 border-b border-slate-200 dark:border-white/10 mb-2 flex items-center gap-3">
              <button
                type="button"
                onClick={toggleTheme}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/20 transition-all text-slate-700 dark:text-zinc-200"
              >
                <Icon name={theme === 'dark' ? 'sun' : 'moon'} className="w-4 h-4" />
                <span className="text-sm font-medium">
                  {t(theme === 'dark' ? 'settings.theme.light' : 'settings.theme.dark')}
                </span>
              </button>
              <LanguageSelector variant="menu" />
            </div>

            {/* Single sign-on accounts have no password here */}
            {user.has_password && (
              <MenuItem
                icon={ICON_PATHS.key}
                label={t('auth.changePassword.title')}
                onClick={() => go('/change-password')}
                iconClassName={`${plainItem} group-hover:bg-accent-500 dark:group-hover:bg-accent-600`}
                className="hover:bg-slate-100 dark:hover:bg-white/10"
              />
            )}

            {user.role === 'administrator' && (
              <MenuItem
                icon="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
                label={t('nav.admin')}
                onClick={() => go('/admin')}
                iconClassName="bg-gradient-to-br from-purple-500 to-pink-600 text-white shadow-lg"
                className="hover:bg-slate-100 dark:hover:bg-white/10"
              />
            )}

            <div className="border-t border-slate-200 dark:border-white/10 my-2" />

            <MenuItem
              icon="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
              label={t('auth.logout')}
              onClick={handleLogout}
              iconClassName={`${plainItem} group-hover:bg-red-600`}
              className="hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30"
            />
          </div>
        </div>,
        document.body
      )}
    </>
  );
};
