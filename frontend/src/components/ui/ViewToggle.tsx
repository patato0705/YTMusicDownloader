// src/components/ui/ViewToggle.tsx
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';

export type ViewMode = 'grid' | 'list';

interface ViewToggleProps {
  value: ViewMode;
  onChange: (mode: ViewMode) => void;
  className?: string;
}

const ICONS: Record<ViewMode, { labelKey: string; path: string }> = {
  grid: {
    labelKey: 'library.view.grid',
    path: 'M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z',
  },
  list: {
    labelKey: 'library.view.list',
    path: 'M4 6h16M4 12h16M4 18h16',
  },
};

/** Segmented grid/list switch, styled like the filter tabs so they sit on one line */
export const ViewToggle: React.FC<ViewToggleProps> = ({ value, onChange, className = '' }) => {
  const { t } = useI18n();

  return (
    <div role="group" className={`flex items-center gap-1 glass rounded-2xl p-2 shrink-0 ${className}`}>
      {(Object.keys(ICONS) as ViewMode[]).map((mode) => {
        const active = value === mode;
        return (
          <button
            key={mode}
            type="button"
            onClick={() => onChange(mode)}
            aria-pressed={active}
            aria-label={t(ICONS[mode].labelKey)}
            title={t(ICONS[mode].labelKey)}
            className={`p-2 rounded-xl transition-all duration-300 ${
              active
                ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
            }`}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d={ICONS[mode].path} />
            </svg>
          </button>
        );
      })}
    </div>
  );
};
