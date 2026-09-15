// src/components/ui/StatCard.tsx
import React from 'react';
import { InfoTooltip } from './InfoTooltip';

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  trend?: string;
  loading?: boolean;
  className?: string;
  /** Optional tooltip text shown next to the label via a small info icon. */
  info?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  icon,
  label,
  value,
  trend,
  loading,
  className = '',
  info,
}) => {
  return (
    <div className={`relative group overflow-hidden rounded-xl glass border-slate-200 dark:border-white/10 p-6 hover:border-blue-400/50 dark:hover:border-red-600/50 transition-all duration-300 ${className}`}>
      {/* Hover glow effect */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-500/0 to-indigo-500/0 dark:from-red-900/0 dark:to-red-800/0 group-hover:from-blue-500/10 group-hover:to-indigo-500/10 dark:group-hover:from-red-900/20 dark:group-hover:to-red-800/15 transition-all duration-300" />

      <div className="relative z-10">
        <div className="flex items-center justify-between mb-3">
          <div className="text-blue-600 dark:text-red-500">{icon}</div>
          {trend && !loading && (
            <span className="text-xs font-medium text-green-600 dark:text-green-400">{trend}</span>
          )}
        </div>

        <div className="text-3xl font-bold text-foreground mb-1">
          {value}
        </div>

        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <span>{label}</span>
          {info && <InfoTooltip label={info} content={info} />}
        </div>
      </div>
    </div>
  );
};
