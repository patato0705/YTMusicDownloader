// src/components/playlists/PlaylistsPanel.tsx
/**
 * The Library's Playlists tab: every playlist added to the library, how it's
 * added, how much of it is in the library, its last scan. Members and admins
 * can rescan a followed one, change its options or remove it.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../../contexts/I18nContext';
import { useAuth } from '../../contexts/AuthContext';
import { useJobActivity } from '../../contexts/JobActivityContext';
import { syncPlaylist } from '../../api/playlists';
import type { SavedPlaylist } from '../../api/playlists';
import { getImageUrl } from '../../api/media';
import { Artwork } from '../ui/Artwork';
import { Button } from '../ui/Button';
import { Spinner } from '../ui/Spinner';
import { Toast } from '../ui/Toast';
import { PlaylistBadges, usePlaylistStats } from './PlaylistBadges';
import { PlaylistOptionsDialog } from './PlaylistOptionsDialog';
import { apiErrorMessage } from '../../utils';

interface PlaylistsPanelProps {
  playlists: SavedPlaylist[];
  /** Something changed: reload the list */
  onChanged: () => void;
}

export const PlaylistsPanel: React.FC<PlaylistsPanelProps> = ({ playlists, onChanged }) => {
  const { t, formatLocale } = useI18n();
  const { user } = useAuth();
  const { refresh: refreshJobs } = useJobActivity();
  const navigate = useNavigate();
  const canModify = user?.role === 'administrator' || user?.role === 'member';
  const playlistStats = usePlaylistStats();
  const [editing, setEditing] = useState<SavedPlaylist | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const lastScan = (p: SavedPlaylist): string | null => {
    if (!p.last_synced_at) return null;
    const when = new Intl.DateTimeFormat(formatLocale, { dateStyle: 'medium', timeStyle: 'short' })
      .format(new Date(p.last_synced_at));
    return t('playlist.status.lastScan', { when });
  };

  const sync = async (p: SavedPlaylist) => {
    setSyncingId(p.id);
    try {
      await syncPlaylist(p.id);
      refreshJobs();
      onChanged();
      setToast({ message: t('playlist.status.syncQueued'), type: 'success' });
    } catch (err: any) {
      setToast({ message: apiErrorMessage(err, t, t('common.error')), type: 'error' });
    } finally {
      setSyncingId(null);
    }
  };

  return (
    <section>
      {playlists.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('library.noPlaylists')}</p>
      ) : (
        <ul className="space-y-3">
          {playlists.map((p) => {
            const scan = lastScan(p);
            return (
              <li
                key={p.id}
                className="glass rounded-2xl p-4 border border-slate-200/50 dark:border-white/10 flex flex-col sm:flex-row sm:items-center gap-4"
              >
                <button
                  type="button"
                  onClick={() => navigate(`/playlist-import?url=${encodeURIComponent(p.id)}`)}
                  className="flex items-center gap-4 min-w-0 flex-1 text-left group"
                >
                  <Artwork
                    src={getImageUrl(p.thumbnail)}
                    name={p.title}
                    seed={p.id}
                    className="w-16 h-16 rounded-xl flex-shrink-0 overflow-hidden ring-1 ring-slate-900/5 dark:ring-white/10"
                  />
                  <div className="min-w-0 space-y-1">
                    <p className="font-semibold text-foreground truncate group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors">
                      {p.title}
                    </p>
                    <PlaylistBadges saved={p} />
                    <p className="text-xs text-muted-foreground">
                      {playlistStats(p)}
                      {p.m3u_file && <> · <span className="font-mono">{p.m3u_file}</span></>}
                    </p>
                    {p.syncing ? (
                      <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                        <Spinner size="sm" className="!w-3 !h-3" /> {t('playlist.status.scanning')}
                      </p>
                    ) : scan ? (
                      <p className="text-xs text-muted-foreground">{scan}</p>
                    ) : null}
                    {p.last_error && !p.syncing && (
                      <p className="text-xs text-red-600 dark:text-red-400 line-clamp-2" title={p.last_error}>
                        {t('playlist.status.lastError', { error: p.last_error })}
                      </p>
                    )}
                  </div>
                </button>

                {canModify && (
                  <div className="flex gap-2 sm:flex-shrink-0">
                    {p.followed && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => sync(p)}
                        isLoading={syncingId === p.id}
                        disabled={p.syncing || syncingId !== null}
                      >
                        {t('playlist.status.syncNow')}
                      </Button>
                    )}
                    <Button variant="secondary" size="sm" onClick={() => setEditing(p)}>
                      {t('playlist.options.editButton')}
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {editing && (
        <PlaylistOptionsDialog
          playlistId={editing.id}
          playlistTitle={editing.title}
          saved={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setToast({ message: t('playlist.options.saved'), type: 'success' });
            refreshJobs();
            onChanged();
          }}
          onRemoved={() => {
            setToast({ message: t('playlist.options.removed'), type: 'success' });
            onChanged();
          }}
        />
      )}

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </section>
  );
};

export default PlaylistsPanel;
