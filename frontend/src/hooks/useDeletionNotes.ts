// src/hooks/useDeletionNotes.ts
import { useI18n } from '../contexts/I18nContext';
import type { DeletionEffects } from '../api/library';

/**
 * The lines a delete confirmation adds about what else changes: the album's
 * artist unfollowed, the followed playlists that would bring it back
 * unfollowed. Empty when nothing does.
 */
export function useDeletionNotes() {
  const { t, locale } = useI18n();
  return (effects: DeletionEffects | null): string => {
    if (!effects) return '';
    const lines: string[] = [];
    if (effects.artist_unfollowed?.name) {
      lines.push(t('library.deletion.artistUnfollowed', { name: effects.artist_unfollowed.name }));
    }
    const playlists = effects.playlists_unfollowed;
    if (playlists.length) {
      const titles = new Intl.ListFormat(locale, { type: 'conjunction' })
        .format(playlists.map((p) => t('library.deletion.quoted', { title: p.title })));
      lines.push(t('library.deletion.playlistsUnfollowed', { titles, count: playlists.length }));
    }
    return lines.join('\n\n');
  };
}
