// src/components/ui/FilterTabs.tsx
import React from 'react';
import { Icon } from './icons';
import type { IconName } from './icons';

export interface FilterTab<T extends string> {
  id: T;
  label: React.ReactNode;
  /** Shown before the label */
  icon?: IconName;
}

interface FilterTabsProps<T extends string> {
  tabs: FilterTab<T>[];
  active: T;
  onChange: (id: T) => void;
  /** Phones: the tabs share the full width, each icon above its label */
  fill?: boolean;
  className?: string;
}

/** Segmented row of buttons picking what a page lists */
export function FilterTabs<T extends string>({ tabs, active, onChange, fill = false, className = '' }: FilterTabsProps<T>): JSX.Element {
  return (
    <div
      role="tablist"
      className={`flex items-center gap-1 sm:gap-2 glass rounded-2xl p-2 ${fill ? 'w-full sm:w-fit' : 'w-fit max-w-full'} ${className}`}
    >
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.id)}
            className={`flex items-center justify-center rounded-xl font-medium whitespace-nowrap transition-all duration-300 ${
              fill
                ? 'flex-1 sm:flex-none flex-col sm:flex-row gap-0.5 sm:gap-2 px-2 sm:px-6 py-2 sm:py-3 text-xs sm:text-base'
                : 'gap-2 px-2.5 sm:px-4 py-2 text-sm sm:text-base'
            } ${
              selected
                ? 'bg-accent-600 text-white shadow-lg'
                : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
            }`}
          >
            {tab.icon && <Icon name={tab.icon} className="w-4 h-4 shrink-0" />}
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
