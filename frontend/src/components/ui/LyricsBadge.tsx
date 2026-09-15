// src/components/ui/LyricsBadge.tsx
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import type { LyricsKind } from '../../types';

interface LyricsBadgeProps {
  kind: LyricsKind | undefined;
  /** Renders as a button when set; otherwise a static pill */
  onClick?: () => void;
  title?: string;
}

/**
 * Pill showing what kind of .lrc a track has: synced (timestamped), plain,
 * or none. Styled like the status badges on the album track list.
 */
export const LyricsBadge: React.FC<LyricsBadgeProps> = ({ kind, onClick, title }) => {
  const { t } = useI18n();

  const config = kind === 'synced'
    ? {
        styles: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30 dark:border-green-500/25',
        label: t('lyrics.kind.synced'),
        icon: (
          <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      }
    : kind === 'plain'
      ? {
          styles: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 dark:border-amber-500/25',
          label: t('lyrics.kind.plain'),
          icon: (
            <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h10" />
            </svg>
          ),
        }
      : {
          styles: 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-400/20 dark:border-slate-500/20',
          label: t('lyrics.kind.none'),
          icon: (
            <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
            </svg>
          ),
        };

  const className = `inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border backdrop-blur-sm ${config.styles}`;

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        title={title}
        className={`${className} hover:ring-2 hover:ring-blue-500/40 dark:hover:ring-red-500/40 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 transition-shadow`}
      >
        {config.icon}
        <span>{config.label}</span>
      </button>
    );
  }

  return (
    <span className={className} title={title}>
      {config.icon}
      <span>{config.label}</span>
    </span>
  );
};
