// src/components/ui/FilterTabs.tsx
import React, { useEffect, useRef } from 'react';
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

/**
 * Segmented row of buttons picking what a page lists. Too wide for the screen
 * (long counts, a narrow phone), it scrolls sideways instead of widening the
 * page.
 */
export function FilterTabs<T extends string>({ tabs, active, onChange, fill = false, className = '' }: FilterTabsProps<T>): JSX.Element {
  const listRef = useRef<HTMLDivElement>(null);

  // The active tab in sight when the row scrolls (e.g. the last one, opened
  // from the URL). Only the row moves: scrollIntoView would scroll the page too.
  useEffect(() => {
    const list = listRef.current;
    const tab = list?.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!list || !tab) return;
    const row = list.getBoundingClientRect();
    const rect = tab.getBoundingClientRect();
    // The row's own padding (p-2) kept around the tab
    const pad = 8;
    if (rect.left < row.left + pad) list.scrollLeft += rect.left - row.left - pad;
    else if (rect.right > row.right - pad) list.scrollLeft += rect.right - row.right + pad;
  }, [active]);

  return (
    <div
      ref={listRef}
      role="tablist"
      className={`flex items-center gap-1 sm:gap-2 glass rounded-2xl p-2 overflow-x-auto no-scrollbar ${fill ? 'w-full sm:w-fit' : 'w-fit max-w-full'} ${className}`}
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
