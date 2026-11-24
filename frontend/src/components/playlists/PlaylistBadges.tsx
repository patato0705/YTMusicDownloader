// src/components/playlists/PlaylistBadges.tsx
/** How a playlist is added to the library, as small chips: mode, followed or once, M3U. */
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import type { SavedPlaylist } from '../../api/playlists';

const chip = 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border';
const accent = 'bg-accent-500/10 text-accent-700 border-accent-500/30 dark:text-accent-400';
const muted = 'border-slate-300/70 dark:border-white/10 text-muted-foreground';

export const PlaylistBadges: React.FC<{ saved: SavedPlaylist; className?: string }> = ({ saved, className = '' }) => {
  const { t } = useI18n();
  return (
    <div className={`flex flex-wrap gap-1.5 ${className}`}>
      <span className={`${chip} ${accent}`}>{t(`playlist.options.${saved.mode}`)}</span>
      <span className={`${chip} ${saved.followed ? accent : muted}`}>
        {t(saved.followed ? 'playlist.status.followed' : 'playlist.status.once')}
      </span>
      {saved.m3u && <span className={`${chip} ${accent}`}>M3U</span>}
    </div>
  );
};

/** "128 of 140 songs in the library · 3 skipped" */
export const usePlaylistStats = () => {
  const { t } = useI18n();
  return (saved: SavedPlaylist): string => {
    const parts = [t('playlist.status.available', { available: saved.available, songs: saved.songs })];
    if (saved.skipped) parts.push(t('playlist.status.skipped', { count: saved.skipped }));
    return parts.join(' · ');
  };
};
