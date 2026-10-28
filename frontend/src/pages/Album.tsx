// src/pages/Album.tsx
import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { useAuth } from '../contexts/AuthContext';
import { useJobActivity } from '../contexts/JobActivityContext';
import { getAlbum, downloadAlbum, retryAlbum } from '../api/albums';
import type { AlbumPage } from '../api/albums';
import { deleteLibraryAlbum, getAlbumDeletionEffects } from '../api/library';
import type { DeletionEffects } from '../api/library';
import { getImageUrl } from '../api/media';
import { useDeletionNotes } from '../hooks/useDeletionNotes';
import { albumTypeKey } from '../components/MediaCard';
import { Artwork } from '../components/ui/Artwork';
import { Button } from '../components/ui/Button';
import { Toast } from '../components/ui/Toast';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { SectionHeader } from '../components/ui/SectionHeader';
import { LyricsBadge } from '../components/ui/LyricsBadge';
import { LyricsModal } from '../components/ui/LyricsModal';
import { GenreChips } from '../components/ui/GenreChips';
import { TrackStatusBadge } from '../components/ui/TrackStatusBadge';
import { EmptyState, ErrorBanner, LoadingState } from '../components/ui/PageStatus';
import { formatDuration, primaryArtistName, apiErrorMessage, artistPath } from '../utils';
import type { Track } from '../types';
import { Icon } from '../components/ui/icons';
import { TH_CLASS } from '../components/ui/tableStyles';

export default function Album(): JSX.Element {
  const { albumId } = useParams<{ albumId: string }>();
  const [page, setPage] = useState<AlbumPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [retryLoading, setRetryLoading] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  // What else the deletion changes, read when the confirmation opens
  const [deleteEffects, setDeleteEffects] = useState<DeletionEffects | null>(null);
  const deletionNotes = useDeletionNotes();
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [lyricsTrack, setLyricsTrack] = useState<Track | null>(null);
  const navigate = useNavigate();
  const { t } = useI18n();
  const { user } = useAuth();
  const { revision, refresh: refreshJobs, downloadsPausedUntil } = useJobActivity();
  // The queue revision the album on screen is up to date with
  const fetchedRevision = useRef(revision);
  const isAdmin = user?.role === 'administrator';
  // Visitors are read-only: downloading and editing lyrics are member+ actions
  const canModify = isAdmin || user?.role === 'member';

  const fetchAlbum = async (id: string): Promise<AlbumPage> => {
    fetchedRevision.current = revision;
    return getAlbum(id);
  };

  useEffect(() => {
    if (!albumId) return;
    let cancelled = false;

    setLoading(true);
    setError(null);
    fetchAlbum(albumId)
      .then((data) => { if (!cancelled) setPage(data); })
      .catch((err) => {
        console.error('Failed to load album:', err);
        if (!cancelled) setError(apiErrorMessage(err, t, t('album.notFound')));
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [albumId]);

  // Follow the job queue, so the track badges move with the download.
  // Albums served from YTMusic have no download to follow, and refetching
  // them would mean a call to YouTube Music each time.
  const source = page?.source;
  useEffect(() => {
    if (!albumId || source !== 'database' || revision === fetchedRevision.current) return;
    let cancelled = false;

    fetchAlbum(albumId)
      .then((data) => { if (!cancelled) setPage(data); })
      .catch((err) => console.error('Failed to refresh album:', err));

    return () => { cancelled = true; };
  }, [albumId, revision, source]);

  if (loading) return <LoadingState />;

  if (error || !page) {
    return (
      <div className="space-y-6 py-8">
        <ErrorBanner title={t('common.error')}>{error || t('album.notFound')}</ErrorBanner>
        <Button onClick={() => navigate('/browse')} variant="primary">
          ← {t('common.back')}
        </Button>
      </div>
    );
  }

  const { album, tracks } = page;
  const id = albumId!;
  const isFollowing = page.mode === 'download';
  // Lyrics and download state only exist for tracks in our DB
  const showTrackState = page.source === 'database';
  // On disk is the norm: the status column only appears for the exceptions
  const showStatus = showTrackState && tracks.some((tr) => tr.status && tr.status !== 'done');
  // Tracks a retry would queue: failed ones, and any left without a job
  const retryableCount = tracks.filter((tr) => tr.status === 'failed' || tr.status === 'available').length;
  const totalDuration = tracks.reduce((sum, track) => sum + (track.duration || 0), 0);

  const handleDownload = async () => {
    setActionLoading(true);
    try {
      const result = await downloadAlbum(id);
      setToast({
        message: t(result.artist_subscription_created ? 'album.downloadQueuedWithArtist' : 'album.downloadQueued'),
        type: 'success',
      });
      refreshJobs();
      setPage((current) => current && { ...current, mode: 'download' });
      // In the DB now: reloaded once, then followed with the job queue. The
      // download is queued even if this reload fails.
      fetchAlbum(id)
        .then(setPage)
        .catch((err) => console.error('Failed to reload album:', err));
    } catch (err: any) {
      console.error('Download failed:', err);
      setToast({ message: apiErrorMessage(err, t, t('album.downloadFailed')), type: 'error' });
    } finally {
      setActionLoading(false);
    }
  };

  // The tracks it queues show up with the job queue's next move
  const handleRetry = async () => {
    setRetryLoading(true);
    try {
      const { tracks_queued, import_queued } = await retryAlbum(id);
      refreshJobs();
      setToast({
        message: import_queued
          ? t('album.retryImport')
          : tracks_queued > 0
            ? t('album.retryQueued', { count: tracks_queued })
            : t('album.retryNothing'),
        type: 'success',
      });
    } catch (err: any) {
      console.error('Retry failed:', err);
      setToast({ message: apiErrorMessage(err, t, t('album.retryFailed')), type: 'error' });
    } finally {
      setRetryLoading(false);
    }
  };

  const openDeleteConfirm = async () => {
    setDeleteEffects(null);
    try {
      setDeleteEffects(await getAlbumDeletionEffects(id));
    } catch (err) {
      console.error('Failed to read what the deletion changes:', err);
    }
    setDeleteConfirm(true);
  };

  const handleDelete = async () => {
    setDeleteLoading(true);
    try {
      await deleteLibraryAlbum(id);
      setToast({ message: t('album.deleted'), type: 'success' });
      setTimeout(() => navigate('/library'), 1500);
    } catch (err: any) {
      console.error('Delete failed:', err);
      setToast({ message: apiErrorMessage(err, t, t('common.error')), type: 'error' });
    } finally {
      setDeleteLoading(false);
      setDeleteConfirm(false);
    }
  };

  const thClass = `px-3 md:px-6 ${TH_CLASS}`;

  return (
    <>
      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
      )}

      <ConfirmDialog
        isOpen={deleteConfirm}
        title={t('album.deleteTitle')}
        message={[t('album.deleteMessage'), deletionNotes(deleteEffects)].filter(Boolean).join('\n\n')}
        confirmText={t('common.delete')}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm(false)}
        variant="danger"
        isLoading={deleteLoading}
      />

      {lyricsTrack && (
        <LyricsModal
          track={lyricsTrack}
          canEdit={canModify}
          onClose={() => setLyricsTrack(null)}
          onSaved={(updated) => {
            setPage((current) => current && {
              ...current,
              tracks: current.tracks.map((tr) => (tr.id === updated.id ? updated : tr)),
            });
            setToast({ message: t('lyrics.saved'), type: 'success' });
          }}
        />
      )}

      <div className="space-y-12 pb-12">
        {/* Album header */}
        <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-8 md:p-12 border border-slate-200/50 dark:border-white/10">
          <div className="flex flex-col md:flex-row gap-8 items-start md:items-center">
            <div className="relative group">
              <Artwork
                src={getImageUrl(album.thumbnail)}
                name={album.title}
                seed={album.id}
                loading="eager"
                className="w-64 h-64 md:w-80 md:h-80 rounded-2xl bg-slate-200 dark:bg-zinc-800 shadow-2xl ring-4 ring-white/50 dark:ring-white/10 group-hover:scale-105 transition-transform duration-300"
              />
              {/* Glow effect */}
              <div className="absolute inset-0 rounded-2xl bg-accent-500/20 blur-2xl -z-10 group-hover:opacity-75 opacity-0 transition-opacity duration-300" />
            </div>

            <div className="flex-1">
              <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-foreground mb-3">{album.title}</h1>

              {album.artist?.name && (
                album.artist.id ? (
                  <Link
                    to={artistPath(album.artist.id)}
                    className="block w-fit text-xl text-accent-600 dark:text-accent-400 hover:underline mb-4 transition-colors"
                  >
                    {album.artist.name}
                  </Link>
                ) : (
                  <p className="text-xl text-accent-600 dark:text-accent-400 mb-4">{album.artist.name}</p>
                )
              )}

              <GenreChips genres={album.genres} className="mb-4" />

              <div className="flex flex-wrap items-center gap-3 text-muted-foreground mb-8">
                <span className="flex items-center gap-2">
                  <Icon name="disc" className="w-4 h-4" />
                  {t(albumTypeKey(album.type))}
                </span>
                <span aria-hidden="true">•</span>
                {album.year && (
                  <>
                    <span className="flex items-center gap-2">
                      <Icon name="calendar" className="w-4 h-4" />
                      {album.year}
                    </span>
                    <span aria-hidden="true">•</span>
                  </>
                )}
                <span className="flex items-center gap-2">
                  <Icon name="music" className="w-4 h-4" />
                  {t('album.trackCount', { count: tracks.length })}
                </span>
                {totalDuration > 0 && (
                  <>
                    <span aria-hidden="true">•</span>
                    <span className="flex items-center gap-2">
                      <Icon name="clock" className="w-4 h-4" />
                      {formatDuration(totalDuration)}
                    </span>
                  </>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                {/* Visitors only get the (inert) "in library" indicator */}
                {(canModify || isFollowing) && (
                  <Button
                    onClick={handleDownload}
                    isLoading={actionLoading}
                    variant={isFollowing ? 'secondary' : 'primary'}
                    size="lg"
                    disabled={isFollowing}
                  >
                    {isFollowing ? <span className="mr-2" aria-hidden="true">✓</span> : <Icon name="download" className="w-5 h-5 mr-2" />}
                    {isFollowing ? t('album.following') : t('album.download')}
                  </Button>
                )}

                {canModify && isFollowing && showTrackState && (retryableCount > 0 || page.needs_import) && (
                  <Button onClick={handleRetry} variant="secondary" size="lg" isLoading={retryLoading}>
                    <span className="mr-2" aria-hidden="true">↻</span>
                    {t('album.retry')}
                  </Button>
                )}

                {/* Last and quiet: it opens a confirmation, the dialog carries the red */}
                {isAdmin && isFollowing && (
                  <Button onClick={openDeleteConfirm} variant="subtleDanger" isLoading={deleteLoading} className="md:ml-auto">
                    {t('album.deleteAlbum')}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        {tracks.length > 0 ? (
          <section>
            <SectionHeader>{t('album.trackList')}</SectionHeader>

            <div className="glass rounded-2xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-100/50 dark:bg-white/5 border-b border-slate-200 dark:border-white/10">
                    <tr>
                      <th className={`${thClass} text-left w-10 md:w-12`}>#</th>
                      <th className={`${thClass} text-left`}>{t('album.title')}</th>
                      <th className={`${thClass} text-left hidden lg:table-cell`}>{t('album.artist')}</th>
                      <th className={`${thClass} text-right hidden sm:table-cell sm:w-24`}>{t('album.duration')}</th>
                      {showTrackState && <th className={`${thClass} text-center w-12 sm:w-24`}>{t('album.lyrics')}</th>}
                      {showStatus && <th className={`${thClass} text-center sm:w-28`}>{t('album.status')}</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-white/10">
                    {tracks.map((track, index) => (
                      <tr key={track.id} className="hover:bg-slate-50 dark:hover:bg-white/5 transition-colors group">
                        <td className="px-3 md:px-6 py-4 text-sm text-muted-foreground font-medium">
                          {track.track_number || index + 1}
                        </td>
                        <td className="px-3 md:px-6 py-4">
                          <div className="font-semibold text-foreground group-hover:text-accent-600 dark:group-hover:text-accent-400 transition-colors">
                            {track.title}
                          </div>
                          <div className="sm:hidden text-xs text-muted-foreground font-mono mt-0.5">
                            {formatDuration(track.duration)}
                          </div>
                        </td>
                        <td className="px-3 md:px-6 py-4 text-sm text-muted-foreground hidden lg:table-cell">
                          {primaryArtistName(track) || t('album.unknownArtist')}
                        </td>
                        <td className="px-3 md:px-6 py-4 text-sm text-muted-foreground text-right font-mono hidden sm:table-cell">
                          {formatDuration(track.duration)}
                        </td>
                        {/* A download-mode album whose import hasn't landed yet
                            lists YTMusic's tracks, which have no row (and no status) */}
                        {showTrackState && (
                          <td className="px-3 md:px-6 py-4 text-center">
                            {track.status && (
                              <LyricsBadge
                                iconOnly
                                kind={track.lyrics}
                                title={t('lyrics.open')}
                                onClick={() => setLyricsTrack(track)}
                              />
                            )}
                          </td>
                        )}
                        {showStatus && (
                          <td className="px-3 md:px-6 py-4 text-center">
                            <TrackStatusBadge track={track} downloadsPausedUntil={downloadsPausedUntil} />
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : (
          <EmptyState icon="music" title={t('album.noTracks')}>
            <p>{t('album.noTracksDescription')}</p>
          </EmptyState>
        )}
      </div>
    </>
  );
}
