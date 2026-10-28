// src/pages/Home.tsx
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { useJobActivity } from '../contexts/JobActivityContext';
import { SectionHeader } from '../components/ui/SectionHeader';
import { ActionCard } from '../components/ui/ActionCard';
import { buttonClass } from '../components/ui/Button';
import { PageHeader } from '../components/ui/PageHeader';
import { getLibraryStats, getLibraryAlbums } from '../api/library';
import type { LibraryAlbum, LibraryStats } from '../api/library';
import { getImageUrl } from '../api/media';
import { MediaCard } from '../components/MediaCard';
import { MediaList, MediaRow } from '../components/MediaList';
import { EmptyState, LoadingState } from '../components/ui/PageStatus';
import { LibraryStatCards } from '../components/LibraryStatCards';
import { Icon } from '../components/ui/icons';
import { albumPath, exceptionalStatus, getAlbumStatus } from '../utils';
import type { MediaStatus } from '../types';

/** Albums still being fetched (or stuck): the reason to open Home */
const IN_PROGRESS_SHOWN = 5;
// Moving first, then stuck, then waiting: a bulk import's queue can't hide the album being fetched
const PROGRESS_ORDER: MediaStatus[] = ['downloading', 'failed', 'queued'];
/** Shortest gap between two refreshes triggered by the job queue */
const REFRESH_MIN_GAP_MS = 5000;

export default function Home(): JSX.Element {
  const { user } = useAuth();
  const { t } = useI18n();
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [recentAlbums, setRecentAlbums] = useState<LibraryAlbum[]>([]);
  const [inProgress, setInProgress] = useState<LibraryAlbum[]>([]);
  const [loading, setLoading] = useState(true);

  const { revision } = useJobActivity();
  // When the last load started, and which one is the latest (an older answer is dropped)
  const lastLoadRef = useRef({ startedAt: 0, id: 0 });

  // Load on mount, then again whenever the job queue moves, so the progress
  // follows downloads. While they run the queue moves every few seconds, so
  // loads are spaced at least REFRESH_MIN_GAP_MS apart.
  useEffect(() => {
    const last = lastLoadRef.current;

    // A load already under way still lands: only a newer one replaces it
    const load = async () => {
      last.startedAt = Date.now();
      const id = ++last.id;
      try {
        const [statsData, albumsData, unfinished] = await Promise.all([
          getLibraryStats(),
          getLibraryAlbums({ limit: 6, sort_by: 'created_at', order: 'desc' }),
          // Its own failure (e.g. a backend without multi-status filtering) only empties this section
          getLibraryAlbums({ statuses: ['downloading', 'pending', 'failed'] }).catch(() => [] as LibraryAlbum[]),
        ]);
        if (id !== last.id) return;
        setStats(statsData);
        setRecentAlbums(albumsData);
        const rank = (album: LibraryAlbum) => PROGRESS_ORDER.indexOf(getAlbumStatus(album));
        setInProgress([...unfinished].sort((a, b) => rank(a) - rank(b)).slice(0, IN_PROGRESS_SHOWN));
      } catch (err) {
        console.error('Failed to load home data:', err);
      } finally {
        if (id === last.id) setLoading(false);
      }
    };

    const timer = window.setTimeout(load, last.startedAt ? Math.max(0, last.startedAt + REFRESH_MIN_GAP_MS - Date.now()) : 0);
    return () => window.clearTimeout(timer);
  }, [revision]);

  // Leaving the page: whatever is still loading is dropped
  useEffect(() => {
    const last = lastLoadRef.current;
    return () => { last.id += 1; };
  }, []);

  return (
    <div className="space-y-8 pb-12">
      <PageHeader icon="home" title={<>{t('home.welcomeBack')} {user?.username}</>} />

      <LibraryStatCards stats={stats} loading={loading} />

      {/* Where to start: the ways music gets into the library */}
      <section>
        <SectionHeader>{t('home.quickActions')}</SectionHeader>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
          <ActionCard to="/browse" icon="search" title={t('nav.browse')} description={t('home.browseDescription')} />
          <ActionCard to="/playlist-import" icon="link" title={t('playlist.title')} description={t('home.playlistDescription')} />
          <ActionCard to="/library" icon="library" title={t('nav.library')} description={t('home.libraryDescription')} />
        </div>
      </section>

      {inProgress.length > 0 && (
        <section>
          <SectionHeader>{t('home.inProgress')}</SectionHeader>
          <MediaList kind="album">
            {inProgress.map((album) => (
              <MediaRow
                key={album.id}
                id={album.id}
                title={album.title}
                subtitle={album.artist?.name}
                thumbnail={getImageUrl(album.thumbnail)}
                type="album"
                albumType={album.type}
                year={album.year ?? undefined}
                mediaStatus={getAlbumStatus(album)}
                tracksTotal={album.tracks_total}
                tracksDownloaded={album.tracks_downloaded}
                date={album.created_at}
                to={albumPath(album.id)}
              />
            ))}
          </MediaList>
        </section>
      )}

      <section>
        <SectionHeader>{t('home.recentlyAdded')}</SectionHeader>
        {loading ? (
          <LoadingState message={t('home.loadingActivity')} className="py-16" />
        ) : recentAlbums.length > 0 ? (
          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3 sm:gap-4">
            {recentAlbums.map((album) => (
              <MediaCard
                key={album.id}
                id={album.id}
                title={album.title}
                subtitle={album.artist?.name}
                thumbnail={getImageUrl(album.thumbnail)}
                type="album"
                albumType={album.type}
                mediaStatus={exceptionalStatus(getAlbumStatus(album))}
                to={albumPath(album.id)}
              />
            ))}
          </div>
        ) : (
          <EmptyState icon="music" title={t('home.noActivity')}>
            <p>{t('home.noActivityDescription')}</p>
            <Link
              to="/browse"
              className={`${buttonClass('primary', 'lg')} gap-2`}
            >
              <Icon name="search" />
              {t('home.browseMusic')}
            </Link>
          </EmptyState>
        )}
      </section>
    </div>
  );
}
