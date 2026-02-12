// src/pages/Library.tsx
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { getLibraryArtists, getLibraryAlbums, getLibraryStats } from '../api/library';
import { getImageUrl } from '../api/media';
import MediaCard from '../components/MediaCard';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { StatCard } from '../components/ui/StatCard';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import { formatNumber } from '../utils';

// Icon components
const ArtistsIcon = () => <span className="text-2xl">🎤</span>;
const AlbumsIcon = () => <span className="text-2xl">💿</span>;
const TracksIcon = () => <span className="text-2xl">🎵</span>;
const DownloadIcon = () => <span className="text-2xl">⬇️</span>;
const LibraryIcon = () => <span className="text-2xl">📚</span>;
const SearchIcon = () => <span className="text-2xl">🔍</span>;

export default function Library(): JSX.Element {
  const [artists, setArtists] = useState<any[]>([]);
  const [albums, setAlbums] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'all' | 'artists' | 'albums'>('all');
  const navigate = useNavigate();
  const { t } = useI18n();

  useEffect(() => {
    loadLibrary();
  }, []);

  const loadLibrary = async () => {
    setLoading(true);
    setError(null);

    try {
      const [artistsResponse, albumsResponse, statsResponse] = await Promise.all([
        getLibraryArtists(),
        getLibraryAlbums(),
        getLibraryStats(),
      ]);

      setArtists((artistsResponse as any)?.artists || artistsResponse || []);
      setAlbums((albumsResponse as any)?.albums || albumsResponse || []);
      setStats(statsResponse || {});
    } catch (err: any) {
      console.error('Failed to load library:', err);
      setError(err.message || 'Failed to load library');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="relative min-h-screen">
        {/* Background effects */}
        <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        <div className="relative z-10 flex items-center justify-center py-20">
          <div className="text-center">
            <Spinner size="lg" className="mx-auto mb-4 text-blue-600 dark:text-red-500" />
            <p className="text-muted-foreground">{t('common.loading')}</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="relative min-h-screen">
        {/* Background effects */}
        <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        <div className="relative z-10 p-6">
          <div className="glass rounded-xl p-6 border border-red-500/50 bg-red-500/5">
            <div className="flex items-center gap-3">
              <span className="text-2xl">⚠️</span>
              <div>
                <h3 className="font-semibold text-red-600 dark:text-red-400 mb-1">
                  {t('common.error')}
                </h3>
                <p className="text-sm text-red-600/80 dark:text-red-400/80">{error}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const hasContent = artists.length > 0 || albums.length > 0;

  // Filter content based on active tab
  const displayedArtists = activeTab === 'albums' ? [] : artists;
  const displayedAlbums = activeTab === 'artists' ? [] : albums;

  return (
    <div className="relative min-h-screen">
      {/* Background effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
      
      {/* Main content */}
      <div className="relative z-10 space-y-12 pb-12">
        {/* Hero section */}
        <PageHero
          title={
            <>
              <span className="text-foreground">Your </span>
              <span className="text-gradient">Music Library</span>
            </>
          }
          subtitle="Manage your followed artists and albums. Track downloads and organize your collection."
        />

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              icon={<ArtistsIcon />}
              label={t('library.stats.artists')}
              value={formatNumber(stats.followed_artists || 0)}
            />
            <StatCard
              icon={<AlbumsIcon />}
              label={t('library.stats.albums')}
              value={formatNumber(stats.followed_albums || 0)}
            />
            <StatCard
              icon={<TracksIcon />}
              label={t('library.stats.tracks')}
              value={formatNumber(stats.total_tracks || 0)}
            />
            <StatCard
              icon={<DownloadIcon />}
              label="Downloaded"
              value={formatNumber(stats.downloaded_tracks || 0)}
            />
          </div>
        )}

        {/* Empty state */}
        {!hasContent ? (
          <div className="glass rounded-2xl p-12 border-gradient">
            <div className="text-center max-w-md mx-auto">
              <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-6">
                <LibraryIcon />
              </div>
              <h3 className="text-2xl font-bold text-foreground mb-3">
                Your library is empty
              </h3>
              <p className="text-muted-foreground mb-8">
                Start building your collection by browsing and following your favorite artists!
              </p>
              <Button
                variant="primary"
                size="lg"
                onClick={() => navigate('/browse')}
                className="gap-2"
              >
                <SearchIcon />
                {t('nav.browse')}
              </Button>
            </div>
          </div>
        ) : (
          <>
            {/* Filter tabs */}
            <div className="flex items-center gap-2 glass rounded-xl p-2 w-fit">
              <button
                onClick={() => setActiveTab('all')}
                className={`px-4 py-2 rounded-lg font-medium transition-all duration-300 ${
                  activeTab === 'all'
                    ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                    : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                }`}
              >
                All
              </button>
              <button
                onClick={() => setActiveTab('artists')}
                className={`px-4 py-2 rounded-lg font-medium transition-all duration-300 ${
                  activeTab === 'artists'
                    ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                    : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                }`}
              >
                Artists ({artists.length})
              </button>
              <button
                onClick={() => setActiveTab('albums')}
                className={`px-4 py-2 rounded-lg font-medium transition-all duration-300 ${
                  activeTab === 'albums'
                    ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                    : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                }`}
              >
                Albums ({albums.length})
              </button>
            </div>

            {/* Followed Artists */}
            {displayedArtists.length > 0 && (
              <section>
                <SectionHeader>
                  {t('library.artists')}
                </SectionHeader>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                  {displayedArtists.map((artist) => (
                    <MediaCard
                      key={artist.id}
                      id={artist.id}
                      title={artist.name}
                      thumbnail={getImageUrl(artist.image_local || artist.thumbnail)}
                      type="artist"
                      onClick={() => navigate(`/artists/${encodeURIComponent(artist.id)}`)}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Followed Albums */}
            {displayedAlbums.length > 0 && (
              <section>
                <SectionHeader>
                  {t('library.albums')}
                </SectionHeader>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                  {displayedAlbums.map((album) => (
                    <MediaCard
                      key={album.id}
                      id={album.id}
                      title={album.title}
                      subtitle={album.artist_name}
                      thumbnail={getImageUrl(album.image_local || album.thumbnail)}
                      type="album"
                      year={album.year}
                      onClick={() => navigate(`/albums/${encodeURIComponent(album.id)}`)}
                    />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}