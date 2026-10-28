// src/components/ui/PageHeader.tsx
import React from 'react';
import { Icon } from './icons';
import type { IconName } from './icons';

interface PageHeaderProps {
  title: React.ReactNode;
  subtitle?: string;
  /** The page's icon, the same as its nav tab */
  icon?: IconName;
  /** Page-level actions, right of the title (below it on phones) */
  actions?: React.ReactNode;
  className?: string;
}

/** A page's title card: compact, so the page's content starts on the first screen */
export const PageHeader: React.FC<PageHeaderProps> = ({ title, subtitle, icon, actions, className = '' }) => (
  <header className={`flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-2xl glass bg-gradient-to-r from-accent-500/10 to-transparent p-5 md:p-7 ${className}`}>
    <div className="flex items-center gap-4 min-w-0">
      {icon && (
        <div className="flex shrink-0 items-center justify-center w-12 h-12 md:w-14 md:h-14 rounded-xl bg-accent-500/15 text-accent-600 dark:text-accent-400">
          <Icon name={icon} className="w-6 h-6 md:w-7 md:h-7" />
        </div>
      )}
      <div className="min-w-0">
        <h1 className="text-2xl md:text-4xl font-bold tracking-tight text-foreground">{title}</h1>
        {subtitle && <p className="mt-1 text-sm md:text-base text-muted-foreground max-w-2xl">{subtitle}</p>}
      </div>
    </div>
    {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
  </header>
);
