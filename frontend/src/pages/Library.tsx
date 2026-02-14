// src/pages/Library.tsx
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { getLibraryArtists, getLibraryAlbums, getLibraryStats } from '../api/library';
import { getImageUrl } from '../api/media';
import MediaCard from '../components/MediaCard';
import { Spinner } from '../components/ui/Spinner';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { formatNumber } from '../utils';

export default function Library(): JSX.Element {
  const [artists, setArtists] = useState<any[]>([]);
  const [albums, setAlbums] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <Spinner size="lg" className="mx-auto mb-4 text-primary" />
          <p className="text-muted-foreground">{t('common.loading')}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-500/10 border border-red-500 text-red-600 dark:text-red-400 rounded-lg">
        {t('common.error')}: {error}
      </div>
    );
  }

  const hasContent = artists.length > 0 || albums.length > 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-foreground mb-2">
          {t('library.title')}
        </h1>
        <p className="text-muted-foreground">
          Your followed artists and albums
        </p>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader>
              <CardDescription>{t('library.stats.artists')}</CardDescription>
              <CardTitle className="text-3xl">
                {formatNumber(stats.followed_artists || 0)}
              </CardTitle>
            </CardHeader>
          </Card>

          <Card>
            <CardHeader>
              <CardDescription>{t('library.stats.albums')}</CardDescription>
              <CardTitle className="text-3xl">
                {formatNumber(stats.followed_albums || 0)}
              </CardTitle>
            </CardHeader>
          </Card>

          <Card>
            <CardHeader>
              <CardDescription>{t('library.stats.tracks')}</CardDescription>
              <CardTitle className="text-3xl">
                {formatNumber(stats.total_tracks || 0)}
              </CardTitle>
            </CardHeader>
          </Card>

          <Card>
            <CardHeader>
              <CardDescription>Downloaded</CardDescription>
              <CardTitle className="text-3xl">
                {formatNumber(stats.downloaded_tracks || 0)}
              </CardTitle>
            </CardHeader>
          </Card>
        </div>
      )}

      {/* Empty state */}
      {!hasContent && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center">
              <div className="text-6xl mb-4">📚</div>
              <h3 className="text-xl font-semibold text-foreground mb-2">
                Your library is empty
              </h3>
              <p className="text-muted-foreground mb-6">
                Start by browsing and following some artists!
              </p>
              <button
                onClick={() => navigate('/browse')}
                className="px-6 py-3 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-lg transition"
              >
                {t('nav.browse')}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Followed Artists */}
      {artists.length > 0 && (
        <section>
          <h2 className="text-2xl font-semibold text-foreground mb-4">
            {t('library.artists')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {artists.map((artist) => (
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
      {albums.length > 0 && (
        <section>
          <h2 className="text-2xl font-semibold text-foreground mb-4">
            {t('library.albums')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {albums.map((album) => (
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
    </div>
  );
}