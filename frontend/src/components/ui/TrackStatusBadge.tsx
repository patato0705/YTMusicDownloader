// src/components/ui/TrackStatusBadge.tsx
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Pill } from './Pill';
import type { Track } from '../../types';
import { ICON_PATHS } from './icons';

interface TrackStatusBadgeProps {
  track: Track;
  /** Set while YouTube has rate-limited us: queued tracks show as paused until then */
  downloadsPausedUntil: string | null;
}

interface Badge {
  tone: string;
  icon: string;
  iconClassName?: string;
  strokeWidth?: number;
  label: string;
  /** Details on hover */
  title?: string;
}

/** A track's download state; nothing for tracks not in the DB */
export const TrackStatusBadge: React.FC<TrackStatusBadgeProps> = ({ track, downloadsPausedUntil }) => {
  const { t, formatLocale } = useI18n();

  const badge = ((): Badge | null => {
    switch (track.status) {
      // Only drawn when the album has exceptions to show: the column is hidden otherwise
      case 'done':
        return {
          tone: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30 dark:border-emerald-500/25',
          icon: ICON_PATHS.check,
          strokeWidth: 2.5,
          label: t('album.trackStatus.done'),
        };
      case 'failed':
        return {
          tone: 'bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30 dark:border-red-500/25',
          icon: ICON_PATHS.alertCircle,
          label: t('album.trackStatus.failed'),
          // The download error, on hover
          title: track.last_error ? `${t('album.downloadError')}: ${track.last_error}` : undefined,
        };
      case 'downloading':
        return {
          tone: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 dark:border-amber-500/25',
          icon: ICON_PATHS.refresh,
          iconClassName: 'animate-spin',
          label: t('album.trackStatus.downloading'),
        };
      case 'queued':
        // Rate-limited: no worker takes downloads until the pause lifts
        if (downloadsPausedUntil) {
          const time = new Date(downloadsPausedUntil).toLocaleTimeString(formatLocale, { hour: '2-digit', minute: '2-digit' });
          return {
            tone: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 dark:border-amber-500/25',
            icon: ICON_PATHS.pauseCircle,
            label: t('album.trackStatus.paused'),
            title: t('album.pausedUntil', { time }),
          };
        }
        // A queued track with an error is waiting out a retry backoff
        return {
          tone: 'bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-400/30 dark:border-slate-500/30',
          icon: ICON_PATHS.hourglass,
          label: t('album.trackStatus.queued'),
          title: track.last_error ? t('album.retryingAfter', { error: track.last_error }) : undefined,
        };
      case 'available':
        return {
          // Quieter than queued by its fill and border; the text still reads (AA)
          tone: 'bg-slate-500/5 text-slate-600 dark:text-slate-400 border-slate-400/15 dark:border-slate-500/15',
          icon: ICON_PATHS.cloud,
          label: t('album.trackStatus.available'),
        };
      default:
        return null;
    }
  })();

  if (!badge) return null;
  const { title, ...pill } = badge;
  return (
    <Pill
      {...pill}
      title={title ?? pill.label}
      labelClassName="hidden sm:inline"
      className={title ? 'cursor-help' : ''}
    />
  );
};
