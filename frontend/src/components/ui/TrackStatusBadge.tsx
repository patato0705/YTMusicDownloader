// src/components/ui/TrackStatusBadge.tsx
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Pill } from './Pill';
import type { Track } from '../../types';

interface TrackStatusBadgeProps {
  track: Track;
  /** Set while YouTube has rate-limited us: queued tracks show as paused until then */
  downloadsPausedUntil: string | null;
}

interface Badge {
  tone: string;
  icon: string;
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
      case 'done':
        return {
          tone: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30 dark:border-green-500/25',
          icon: 'M5 13l4 4L19 7',
          strokeWidth: 2.5,
          label: t('album.trackStatus.done'),
        };
      case 'failed':
        return {
          tone: 'bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30 dark:border-red-500/25',
          icon: 'M6 18L18 6M6 6l12 12',
          strokeWidth: 2.5,
          label: t('album.trackStatus.failed'),
          // The download error, on hover
          title: track.last_error ? `${t('album.downloadError')}: ${track.last_error}` : undefined,
        };
      case 'downloading':
        return {
          tone: 'bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30 dark:border-blue-500/25',
          icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4',
          label: t('album.trackStatus.downloading'),
        };
      case 'queued':
        // Rate-limited: no worker takes downloads until the pause lifts
        if (downloadsPausedUntil) {
          const time = new Date(downloadsPausedUntil).toLocaleTimeString(formatLocale, { hour: '2-digit', minute: '2-digit' });
          return {
            tone: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 dark:border-amber-500/25',
            icon: 'M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z',
            label: t('album.trackStatus.paused'),
            title: t('album.pausedUntil', { time }),
          };
        }
        // A queued track with an error is waiting out a retry backoff
        return {
          tone: 'bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-400/30 dark:border-slate-500/30',
          icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
          label: t('album.trackStatus.queued'),
          title: track.last_error ? t('album.retryingAfter', { error: track.last_error }) : undefined,
        };
      case 'available':
        return {
          tone: 'bg-slate-500/5 text-slate-400 dark:text-slate-500 border-slate-400/15 dark:border-slate-500/15',
          icon: 'M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z',
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
