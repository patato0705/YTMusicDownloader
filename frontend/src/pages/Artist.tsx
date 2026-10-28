// src/pages/Artist.tsx
import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { useAuth } from '../contexts/AuthContext';
import { useJobActivity } from '../contexts/JobActivityContext';
import { getArtist, followArtist, unfollowArtist } from '../api/artists';
import type { ArtistPage, ArtistRelease } from '../api/artists';
import { deleteLibraryArtist, getArtistDeletionEffects } from '../api/library';
import type { DeletionEffects } from '../api/library';
import { getImageUrl } from '../api/media';
import { useDeletionNotes } from '../hooks/useDeletionNotes';
import { useLikeSync } from '../hooks/useLikeSync';
import { MediaCard } from '../components/MediaCard';
import { Artwork } from '../components/ui/Artwork';
import { Button } from '../components/ui/Button';
import { LikeButton } from '../components/ui/LikeButton';
import { Toast } from '../components/ui/Toast';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { SectionHeader } from '../components/ui/SectionHeader';
import { GenreChips } from '../components/ui/GenreChips';
import { EmptyState, ErrorBanner, LoadingState } from '../components/ui/PageStatus';
import { categorizeAlbums, getAlbumStatus, apiErrorMessage, albumPath } from '../utils';

export default function Artist(): JSX.Element {
  const { artistId } = useParams<{ artistId: string }>();
  const [page, setPage] = useState<ArtistPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [unfollowConfirm, setUnfollowConfirm] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  // What else the deletion changes, read when the confirmation opens
  const [deleteEffects, setDeleteEffects] = useState<DeletionEffects | null>(null);
  const deletionNotes = useDeletionNotes();
  const [deleteLoading, setDeleteLoading] = useState(false);
  const navigate = useNavigate();
  const { t } = useI18n();
  const { user } = useAuth();
  const { revision, refresh: refreshJobs } = useJobActivity();
  // The queue revision the artist on screen is up to date with
  const fetchedRevision = useRef(revision);
  const isAdmin = user?.role === 'administrator';
  // Visitors are read-only: follow/unfollow and likes are member+ actions on the backend
  const canFollow = isAdmin || user?.role === 'member';

  // Put back if the server says no
  const likeSync = useLikeSync((_, liked) => {
    setPage((current) => current && { ...current, liked });
    setToast({ message: t('artist.likeError'), type: 'error' });
  });

  const fetchArtist = async (id: string): Promise<ArtistPage> => {
    fetchedRevision.current = revision;
    const data = await getArtist(id);
    // A heart clicked but not saved yet keeps what the screen shows
    const liked = likeSync.unsaved().get(id);
    return liked === undefined ? data : { ...data, liked };
  };

  useEffect(() => {
    if (!artistId) return;
    let cancelled = false;

    setLoading(true);
    setError(null);
    fetchArtist(artistId)
      .then((data) => { if (!cancelled) setPage(data); })
      .catch((err) => {
        console.error('Failed to load artist:', err);
        if (!cancelled) setError(apiErrorMessage(err, t, t('artist.notFound')));
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [artistId]);

  // Keep the album badges in step with the job queue. Only for artists
  // followed in full: for the others this endpoint goes out to YTMusic
  // (see routers/artists.py), far too costly to repeat here.
  const source = page?.source;
  useEffect(() => {
    if (!artistId || source !== 'database' || revision === fetchedRevision.current) return;
    let cancelled = false;

    fetchArtist(artistId)
      .then((data) => { if (!cancelled) setPage(data); })
      .catch((err) => console.error('Failed to refresh artist:', err));

    return () => { cancelled = true; };
  }, [artistId, revision, source]);

  if (loading) return <LoadingState />;

  if (error || !page) {
    return (
      <div className="space-y-6 py-8">
        <ErrorBanner title={t('common.error')}>{error || t('artist.notFound')}</ErrorBanner>
        <Button onClick={() => navigate('/browse')} variant="primary">
          ← {t('common.back')}
        </Button>
      </div>
    );
  }

  const { artist, albums: releases } = page;
  const id = artistId!;
  const followed = page.subscription_mode === 'full';
  // Only artists of the library can be liked: their similar artists are known
  const inLibrary = page.subscription_mode != null;
  const { albums, singles } = categorizeAlbums(releases);

  const setSubscriptionMode = (mode: ArtistPage['subscription_mode']) =>
    setPage((current) => current && { ...current, subscription_mode: mode });

  const handleFollow = async () => {
    if (followed) {
      setUnfollowConfirm(true);
      return;
    }

    setActionLoading(true);
    try {
      await followArtist(id, artist.name);
      // Following likes it too, which a heart click still waiting mustn't undo
      setPage((current) => current && { ...current, subscription_mode: 'full', liked: true });
      if (likeSync.unsaved().has(id)) likeSync.toggle(id, true);
      refreshJobs();
    } catch (err: any) {
      console.error('Follow failed:', err);
      setToast({ message: apiErrorMessage(err, t, t('common.error')), type: 'error' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleUnfollow = async () => {
    setActionLoading(true);
    try {
      await unfollowArtist(id);
      setSubscriptionMode('light');
      refreshJobs();
    } catch (err: any) {
      console.error('Unfollow failed:', err);
      setToast({ message: apiErrorMessage(err, t, t('common.error')), type: 'error' });
    } finally {
      setActionLoading(false);
      setUnfollowConfirm(false);
    }
  };

  // Flipped right away; the server hears of it once the clicks stop (useLikeSync)
  const toggleLike = () => {
    const liked = !page.liked;
    setPage((current) => current && { ...current, liked });
    likeSync.toggle(id, liked);
  };

  const openDeleteConfirm = async () => {
    setDeleteEffects(null);
    try {
      setDeleteEffects(await getArtistDeletionEffects(id));
    } catch (err) {
      console.error('Failed to read what the deletion changes:', err);
    }
    setDeleteConfirm(true);
  };

  const handleDelete = async () => {
    setDeleteLoading(true);
    try {
      await deleteLibraryArtist(id);
      setToast({ message: t('artist.deleted'), type: 'success' });
      setTimeout(() => navigate('/library'), 1500);
    } catch (err: any) {
      console.error('Delete failed:', err);
      setToast({ message: apiErrorMessage(err, t, t('common.error')), type: 'error' });
    } finally {
      setDeleteLoading(false);
      setDeleteConfirm(false);
    }
  };

  const releaseGrid = (title: string, list: ArtistRelease[]) => list.length > 0 && (
    <section>
      <SectionHeader>{title}</SectionHeader>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        {list.map((album) => (
          <MediaCard
            key={album.id}
            id={album.id}
            title={album.title}
            thumbnail={getImageUrl(album.thumbnail)}
            type="album"
            albumType={album.type}
            year={album.year ?? undefined}
            mediaStatus={getAlbumStatus(album)}
            to={albumPath(album.id)}
          />
        ))}
      </div>
    </section>
  );

  return (
    <>
      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
      )}

      <ConfirmDialog
        isOpen={unfollowConfirm}
        title={t('artist.unfollowTitle')}
        message={t('artist.unfollowMessage')}
        confirmText={t('artist.unfollow')}
        onConfirm={handleUnfollow}
        onCancel={() => setUnfollowConfirm(false)}
        variant="warning"
        isLoading={actionLoading}
      />

      <ConfirmDialog
        isOpen={deleteConfirm}
        title={t('artist.deleteTitle')}
        message={[t('artist.deleteMessage'), deletionNotes(deleteEffects)].filter(Boolean).join('\n\n')}
        confirmText={t('common.delete')}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm(false)}
        variant="danger"
        isLoading={deleteLoading}
      />

      <div className="space-y-12 pb-12">
        {/* Artist header */}
        <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-8 md:p-12 border border-slate-200/50 dark:border-white/10">
          <div className="flex flex-col md:flex-row gap-8 items-start md:items-center">
            <div className="relative group">
              <Artwork
                src={getImageUrl(artist.thumbnail)}
                name={artist.name}
                seed={artist.id}
                loading="eager"
                className="w-48 h-48 md:w-64 md:h-64 rounded-full bg-slate-200 dark:bg-zinc-800 shadow-2xl ring-4 ring-white/50 dark:ring-white/10 group-hover:scale-105 transition-transform duration-300"
              />
              {/* Glow effect */}
              <div className="absolute inset-0 rounded-full bg-accent-500/20 blur-2xl -z-10 group-hover:opacity-75 opacity-0 transition-opacity duration-300" />
            </div>

            <div className="flex-1">
              <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-foreground mb-4">{artist.name}</h1>

              <GenreChips genres={artist.genres} className="mb-4" />

              <p className="text-lg text-muted-foreground mb-8">
                {t('artist.releaseCount', { count: releases.length })}
              </p>

              <div className="flex flex-wrap items-center gap-3">
                {canFollow && (
                  <Button
                    onClick={handleFollow}
                    isLoading={actionLoading}
                    variant={followed ? 'secondary' : 'primary'}
                    size="lg"
                  >
                    <span className="mr-2" aria-hidden="true">{followed ? '✓' : '+'}</span>
                    {followed ? t('artist.unfollow') : t('artist.follow')}
                  </Button>
                )}

                {canFollow && inLibrary && (
                  <LikeButton
                    liked={page.liked}
                    name={artist.name}
                    onToggle={toggleLike}
                    className="w-[52px] h-[52px] border border-slate-200 dark:border-white/10 text-muted-foreground hover:text-foreground hover:bg-slate-200/70 dark:hover:bg-white/10 transition-colors"
                    iconClassName="w-6 h-6"
                  />
                )}

                {/* Last and quiet: it opens a confirmation, the dialog carries the red */}
                {isAdmin && page.subscription_mode != null && (
                  <Button onClick={openDeleteConfirm} variant="subtleDanger" isLoading={deleteLoading} className="md:ml-auto">
                    {t('artist.delete')}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        {releaseGrid(t('artist.albums'), albums)}
        {releaseGrid(t('artist.singles'), singles)}

        {releases.length === 0 && (
          <EmptyState icon="disc" title={t('artist.noAlbums')}>
            <p>{t('artist.noAlbumsDescription')}</p>
          </EmptyState>
        )}
      </div>
    </>
  );
}
