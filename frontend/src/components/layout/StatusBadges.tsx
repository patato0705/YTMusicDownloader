// src/components/layout/StatusBadges.tsx
/**
 * The navbar's status badges: the jobs at work, and the downloads paused by
 * a YouTube rate limit (backend/jobs/gate.py). Each opens a bubble on hover,
 * focus or tap. Also shown, with sample figures, in the welcome tour.
 */
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { InfoTooltip } from '../ui/InfoTooltip';
import { Icon } from '../ui/icons';

// The status badges are 28px tall: this puts their bubbles where the navbar's
// menus open (40px buttons, 20px gap), clear of the navbar. A bubble over the
// navbar's glass blurs the spinning badge, so the browser redraws it, and any
// menu over it, every frame, leaving a flickering seam along the bottom.
const NAVBAR_TOOLTIP_GAP = 26;

interface RateLimitBadgeProps {
  /** When downloads start again (ISO date) */
  until: string;
  /** Pixels between the badge and its bubble (the navbar's by default) */
  gap?: number;
}

export const RateLimitBadge: React.FC<RateLimitBadgeProps> = ({ until, gap = NAVBAR_TOOLTIP_GAP }) => {
  const { formatLocale, t } = useI18n();
  const text = t('nav.rateLimited', {
    time: new Date(until).toLocaleTimeString(formatLocale, { hour: '2-digit', minute: '2-digit' }),
  });
  return (
    <InfoTooltip
      label={text}
      content={text}
      gap={gap}
      className="flex items-center justify-center w-7 h-7 rounded-xl bg-red-500/15 text-red-600 dark:text-red-400 text-sm font-bold"
    >
      !
    </InfoTooltip>
  );
};

interface JobsBadgeProps {
  count: number;
  /** Jobs at work, by type (download_track, download_lyrics...) */
  byType: Record<string, number>;
  gap?: number;
}

export const JobsBadge: React.FC<JobsBadgeProps> = ({ count, byType, gap = NAVBAR_TOOLTIP_GAP }) => {
  const { t, tOr } = useI18n();

  // The badge counts every kind of job, so a finished album can keep it lit
  // while its per-track lyrics fetches drain. Spell out what's actually running.
  const breakdown = Object.entries(byType)
    .filter(([, n]) => n > 0)
    .sort(([, a], [, b]) => b - a);
  const summary = t('nav.activeJobs', { count });

  const content = (
    <>
      <div className="font-medium">{summary}</div>
      {breakdown.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-muted-foreground">
          {breakdown.map(([type, n]) => (
            <li key={type} className="flex justify-between gap-6">
              <span>{tOr(`nav.jobTypes.${type}`, type.replace(/_/g, ' '))}</span>
              <span className="tabular-nums">{n}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );

  return (
    <InfoTooltip
      label={summary}
      content={content}
      gap={gap}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-amber-500/15 text-amber-600 dark:text-amber-400 text-xs font-medium"
    >
      <Icon name="refresh" strokeWidth={2.5} className="w-3.5 h-3.5 animate-spin" />
      <span className="tabular-nums">{count}</span>
    </InfoTooltip>
  );
};
