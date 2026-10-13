// src/components/ui/LyricsBadge.tsx
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Pill } from './Pill';
import type { LyricsKind } from '../../types';

interface LyricsBadgeProps {
  kind: LyricsKind | undefined;
  /** Renders as a button when set; otherwise a static pill */
  onClick?: () => void;
  title?: string;
}

const KINDS = {
  synced: {
    tone: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30 dark:border-green-500/25',
    icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  plain: {
    tone: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 dark:border-amber-500/25',
    icon: 'M4 6h16M4 12h16M4 18h10',
  },
  none: {
    tone: 'bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-400/20 dark:border-slate-500/20',
    icon: 'M20 12H4',
  },
};

/**
 * Pill showing what kind of .lrc a track has: synced (timestamped), plain,
 * or none.
 */
export const LyricsBadge: React.FC<LyricsBadgeProps> = ({ kind, onClick, title }) => {
  const { t } = useI18n();
  const key = kind ?? 'none';
  return <Pill {...KINDS[key]} label={t(`lyrics.kind.${key}`)} title={title} onClick={onClick} />;
};
