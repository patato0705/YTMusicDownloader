// src/components/layout/AppearanceMenu.tsx
import React from 'react';
import { createPortal } from 'react-dom';
import { ACCENTS, useTheme } from '../../contexts/ThemeContext';
import { useI18n } from '../../contexts/I18nContext';
import { useDropdown } from '../../hooks/useDropdown';
import { Icon } from '../ui/icons';

/**
 * A dot per accent colour, the current one outlined and checked. Each dot
 * carries its own data-accent, so bg-accent-500 paints that dot's hue.
 */
export const AccentSwatches: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { accent, setAccent } = useTheme();
  const { t, tOr } = useI18n();

  return (
    <div role="group" aria-label={t('settings.accent.label')} className={`flex items-center gap-2.5 ${className}`}>
      {ACCENTS.map((name) => {
        const selected = name === accent;
        const label = tOr(`settings.accent.colors.${name}`, name);
        return (
          <button
            key={name}
            type="button"
            data-accent={name}
            onClick={() => setAccent(name)}
            aria-pressed={selected}
            aria-label={label}
            title={label}
            // An outline, not a ring: its offset is a see-through gap on the glass menus.
            // Focus outlines in the text colour, so it never passes for the selection.
            className={`w-8 h-8 shrink-0 rounded-full bg-accent-500 flex items-center justify-center text-white transition-transform outline outline-2 outline-offset-2 focus-visible:outline-foreground ${
              selected ? 'outline-accent-500' : 'outline-transparent hover:scale-110'
            }`}
          >
            {selected && <Icon name="check" strokeWidth={3} className="w-4 h-4" />}
          </button>
        );
      })}
    </div>
  );
};

/** Light and dark, side by side */
export const ThemeSwitch: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { theme, setTheme } = useTheme();
  const { t } = useI18n();

  return (
    <div className={`grid grid-cols-2 gap-1 p-1 rounded-xl bg-slate-100 dark:bg-white/10 ${className}`}>
      {(['light', 'dark'] as const).map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => setTheme(option)}
          aria-pressed={theme === option}
          className={`flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
            theme === option
              ? 'bg-white dark:bg-white/15 text-foreground shadow-sm'
              : 'text-slate-600 dark:text-zinc-400 hover:text-foreground'
          }`}
        >
          <Icon name={option === 'light' ? 'sun' : 'moon'} className="w-4 h-4" />
          {t(`settings.theme.${option}`)}
        </button>
      ))}
    </div>
  );
};

/** The navbar's appearance button (md and up): light or dark, and the accent colour */
export const AppearanceMenu: React.FC = () => {
  const { open, toggle, buttonRef, menuRef, menuStyle } = useDropdown('right', 20);
  const { t } = useI18n();
  const title = t('settings.appearance');

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-label={title}
        title={title}
        className="hidden md:block p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-300 group"
      >
        <Icon name="swatch" className="w-5 h-5 text-slate-700 dark:text-zinc-300 group-hover:text-accent-600 dark:group-hover:text-accent-400 transition-colors" />
      </button>

      {open && createPortal(
        <div ref={menuRef} className="fixed w-64 glass-chrome rounded-2xl shadow-xl p-3 z-[60] space-y-3" style={menuStyle}>
          <ThemeSwitch />
          <div>
            <div className="px-1 mb-2 text-xs font-medium text-muted-foreground">{t('settings.accent.label')}</div>
            <AccentSwatches className="px-1" />
          </div>
        </div>,
        document.body
      )}
    </>
  );
};
