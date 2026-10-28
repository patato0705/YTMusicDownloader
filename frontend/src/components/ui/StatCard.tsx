// src/components/ui/StatCard.tsx
import React from 'react';
import { InfoTooltip } from './InfoTooltip';
import { Icon } from './icons';
import type { IconName } from './icons';

interface StatCardProps {
  icon: IconName;
  label: string;
  /** Shown instead of label on phones, where the cards are narrow */
  shortLabel?: string;
  value: React.ReactNode;
  className?: string;
  /** Optional tooltip text shown next to the label via a small info icon. */
  info?: string;
}

/** One figure of a stats grid: an icon, the number, what it counts (read label first) */
export const StatCard: React.FC<StatCardProps> = ({
  icon,
  label,
  shortLabel,
  value,
  className = '',
  info,
}) => {
  return (
    <div className={`flex items-center gap-3 sm:gap-4 glass rounded-xl p-3 sm:p-5 ${className}`}>
      <div className="flex shrink-0 items-center justify-center w-10 h-10 sm:w-12 sm:h-12 rounded-xl bg-accent-500/10 text-accent-600 dark:text-accent-400">
        <Icon name={icon} className="w-5 h-5 sm:w-6 sm:h-6" />
      </div>
      <div className="flex min-w-0 flex-col-reverse">
        <div className="flex items-center gap-1 text-xs sm:text-sm text-muted-foreground">
          {shortLabel && <span className="sm:hidden">{shortLabel}</span>}
          <span className={shortLabel ? 'hidden sm:inline' : 'truncate'}>{label}</span>
          {info && <InfoTooltip label={info} content={info} />}
        </div>
        <div className="text-xl sm:text-3xl font-bold tabular-nums text-foreground whitespace-nowrap">
          {value}
        </div>
      </div>
    </div>
  );
};
