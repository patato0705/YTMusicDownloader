// src/pages/Home.tsx
import { useEffect, useState, memo } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { ActionCard } from '../components/ui/ActionCard';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import { getLibraryStats, getLibraryAlbums } from '../api/library';
import type { LibraryAlbum, LibraryStats } from '../api/library';
import { getImageUrl } from '../api/media';
import { Artwork } from '../components/ui/Artwork';
import { EmptyState, LoadingState } from '../components/ui/PageStatus';
import { LibraryStatCards } from '../components/LibraryStatCards';

const SearchIcon = () => <span className="text-2xl" aria-hidden="true">🔍</span>;
const LibraryIcon = () => <span className="text-2xl" aria-hidden="true">📚</span>;

/**
 * Isolated album card: memoized (and Artwork keeps its own image-error
 * state) so one broken thumbnail never re-renders the rest of the grid.
 */
const AlbumCard = memo(function AlbumCard({ album }: { album: LibraryAlbum }) {
  const { t } = useI18n();

  const thumbnailUrl = getImageUrl(album.thumbnail);
  const progress = album.tracks_total > 0
    ? (album.tracks_downloaded / album.tracks_total) * 100
    : 0;

  return (
    <Link
      to={`/albums/${encodeURIComponent(album.id)}`}
      className="group relative overflow-hidden rounded-xl bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10 border border-slate-200 dark:border-white/10 hover:border-blue-400/50 dark:hover:border-red-600/50 transition-[background-color,border-color,transform] duration-300 hover:-translate-y-1"
    >
      {/* Album art or placeholder */}
      <div className="relative aspect-square overflow-hidden">
        <Artwork
          src={thumbnailUrl}
          name={album.title}
          seed={album.id}
          className="w-full h-full transition-transform duration-300 group-hover:scale-110"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />

        {/* Progress indicator */}
        {progress < 100 && (
          <div className="absolute top-2 right-2 px-2 py-1 rounded-full bg-white/80 dark:bg-black/60 text-xs font-medium text-blue-600 dark:text-red-400">
            {Math.round(progress)}%
          </div>
        )}
      </div>

      {/* Album info */}
      <div className="p-4">
        <h3 className="font-semibold text-foreground truncate mb-1 group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors duration-200">
          {album.title}
        </h3>
        <p className="text-sm text-muted-foreground truncate mb-3">
          {album.artist?.name}
        </p>

        {/* Download progress bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{t('home.tracksDownloaded', { done: album.tracks_downloaded, total: album.tracks_total })}</span>
            {progress === 100 && (
              <span className="text-blue-600 dark:text-red-400">✓ {t('home.complete')}</span>
            )}
          </div>
          <div className="h-1 bg-slate-200 dark:bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-red-700 dark:to-red-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>
    </Link>
  );
});

export default function Home(): JSX.Element {
  const { user } = useAuth();
  const { t } = useI18n();
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [recentAlbums, setRecentAlbums] = useState<LibraryAlbum[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const [statsData, albumsData] = await Promise.all([
          getLibraryStats(),
          getLibraryAlbums({ limit: 6, sort_by: 'created_at', order: 'desc' }),
        ]);
        if (!cancelled) {
          setStats(statsData);
          setRecentAlbums(albumsData);
        }
      } catch (err) {
        console.error('Failed to load home data:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, []);

  return (
    <div className="space-y-12 pb-12">
      <PageHero
        badge={{ text: t('home.badge'), online: true }}
        title={
          <>
            <span className="text-foreground">{t('home.welcomeBack')} </span>
            <span className="text-gradient">{user?.username}</span>
          </>
        }
        subtitle={t('home.heroSubtitle')}
      />

      <LibraryStatCards stats={stats} loading={loading} />

      {/* Quick Actions */}
      <div>
        <SectionHeader>{t('home.quickActions')}</SectionHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ActionCard
            to="/browse"
            icon={<SearchIcon />}
            title={t('nav.browse')}
            description={t('home.browseDescription')}
            gradient="from-blue-500/10 to-indigo-500/10 dark:from-red-900/20 dark:to-red-800/20"
          />

          <ActionCard
            to="/library"
            icon={<LibraryIcon />}
            title={t('nav.library')}
            description={t('home.libraryDescription')}
            gradient="from-indigo-500/10 to-violet-500/10 dark:from-red-900/20 dark:via-purple-900/15 dark:to-red-800/20"
          />
        </div>
      </div>

      {/* Recent Activity */}
      <div>
        <SectionHeader>{t('home.recentActivity')}</SectionHeader>

        <div className="rounded-2xl p-6 bg-white/90 dark:bg-zinc-900/90 border border-slate-200/60 dark:border-white/10 shadow-sm">
          {loading ? (
            <LoadingState message={t('home.loadingActivity')} className="py-16" />
          ) : recentAlbums.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {recentAlbums.map((album) => (
                <AlbumCard key={album.id} album={album} />
              ))}
            </div>
          ) : (
            <EmptyState icon="🎵" title={t('home.noActivity')} bare>
              <p>{t('home.noActivityDescription')}</p>
              <Link
                to="/browse"
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-red-700 dark:to-red-600 text-white font-medium hover:shadow-lg hover:shadow-blue-600/50 dark:hover:shadow-red-700/50 transition-shadow duration-300"
              >
                <SearchIcon />
                {t('home.browseMusic')}
              </Link>
            </EmptyState>
          )}
        </div>
      </div>
    </div>
  );
}
