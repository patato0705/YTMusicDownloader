// src/components/ui/StatCard.tsx
import React, { useState } from 'react';

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
  const [showInfo, setShowInfo] = useState(false);

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
          {info && (
            <span
              className="relative inline-flex"
              onMouseEnter={() => setShowInfo(true)}
              onMouseLeave={() => setShowInfo(false)}
            >
              <button
                type="button"
                onClick={() => setShowInfo((v) => !v)}
                onFocus={() => setShowInfo(true)}
                onBlur={() => setShowInfo(false)}
                aria-label={info}
                className="flex items-center justify-center w-4 h-4 rounded-full border border-slate-300 dark:border-white/20 text-[10px] leading-none text-muted-foreground hover:text-blue-600 dark:hover:text-red-400 hover:border-blue-400/50 dark:hover:border-red-600/50 transition-colors"
              >
                i
              </button>
              {showInfo && (
                <span
                  role="tooltip"
                  className="absolute z-20 bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 px-3 py-2 rounded-lg bg-slate-900 dark:bg-black text-white text-xs leading-snug shadow-lg pointer-events-none"
                >
                  {info}
                  <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900 dark:border-t-black" />
                </span>
              )}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
