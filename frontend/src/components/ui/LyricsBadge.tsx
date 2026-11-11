// src/components/ui/LyricsBadge.tsx
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Pill } from './Pill';
import type { LyricsKind } from '../../types';
import { ICON_PATHS } from './icons';

interface LyricsBadgeProps {
  kind: LyricsKind | undefined;
  /** No lyrics yet because the LRCLIB lookup hasn't run: shown instead of "none" */
  pending?: boolean;
  /** Renders as a button when set; otherwise a static pill */
  onClick?: () => void;
  title?: string;
  /** Just the icon, for a column of them: the kind moves to the hover text */
  iconOnly?: boolean;
}

const KINDS = {
  synced: {
    tone: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30 dark:border-green-500/25',
    icon: ICON_PATHS.clock,
  },
  plain: {
    tone: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 dark:border-amber-500/25',
    icon: ICON_PATHS.lines,
  },
  instrumental: {
    tone: 'bg-violet-500/15 text-violet-700 dark:text-violet-400 border-violet-500/30 dark:border-violet-500/25',
    icon: ICON_PATHS.music,
  },
  pending: {
    tone: 'bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-400/30 dark:border-slate-500/30',
    icon: ICON_PATHS.hourglass,
  },
  none: {
    tone: 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-400/20 dark:border-slate-500/20',
    icon: ICON_PATHS.minus,
  },
};

/**
 * Pill showing what kind of .lrc a track has: synced (timestamped), plain,
 * or none; or that LRCLIB lists the track as instrumental (no .lrc at all),
 * or that its lookup is still to come.
 */
export const LyricsBadge: React.FC<LyricsBadgeProps> = ({ kind, pending = false, onClick, title, iconOnly = false }) => {
  const { t } = useI18n();
  const key = kind ?? (pending ? 'pending' : 'none');
  const label = t(`lyrics.kind.${key}`);
  // Icon only: the kind moves to the hover text, above what clicking does
  const iconOnlyProps = iconOnly
    ? { labelClassName: 'sr-only', className: '!px-1.5', title: title ? `${label}
${title}` : label }
    : { title };
  return <Pill {...KINDS[key]} label={label} onClick={onClick} {...iconOnlyProps} />;
};
