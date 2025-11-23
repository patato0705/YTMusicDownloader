// src/pages/Artist.tsx
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { getArtist, followArtist, unfollowArtist } from '../api/artists';
import MediaCard from '../components/MediaCard';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { categorizeAlbums, getBestThumbnail } from '../utils';
import type { Album } from '../types';

export default function Artist(): JSX.Element {
  const { artistId } = useParams<{ artistId: string }>();
  const [artist, setArtist] = useState<any>(null);
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFollowing, setIsFollowing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const navigate = useNavigate();
  const { t } = useI18n();

  useEffect(() => {
    if (artistId) {
      loadArtist();
    }
  }, [artistId]);

  const loadArtist = async () => {
    if (!artistId) return;

    setLoading(true);
    setError(null);

    try {
      const data = await getArtist(artistId);
      setArtist(data.artist || data);
      
      // Combine albums and singles from API response
      const allAlbums = [
        ...(data.albums || []),
        ...(data.singles || [])
      ];
      setAlbums(allAlbums);
      setIsFollowing(data.followed || false);
    } catch (err: any) {
      console.error('Failed to load artist:', err);
      setError(err.message || 'Failed to load artist');
    } finally {
      setLoading(false);
    }
  };

  const handleFollow = async () => {
    if (!artistId) return;

    setActionLoading(true);
    try {
      if (isFollowing) {
        await unfollowArtist(artistId);
        setIsFollowing(false);
      } else {
        await followArtist(artistId);
        setIsFollowing(true);
      }
    } catch (err: any) {
      console.error('Follow action failed:', err);
      alert(err.message || 'Action failed');
    } finally {
      setActionLoading(false);
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

  if (error || !artist) {
    return (
      <div className="space-y-4">
        <div className="p-4 bg-red-500/10 border border-red-500 text-red-600 dark:text-red-400 rounded-lg">
          {error || 'Artist not found'}
        </div>
        <Button onClick={() => navigate('/browse')}>
          {t('common.back')} to Browse
        </Button>
      </div>
    );
  }

  const { albums: regularAlbums, singles } = categorizeAlbums(albums);

  return (
    <div className="space-y-8">
      {/* Artist header */}
      <div className="flex flex-col md:flex-row gap-6 items-start">
        <img
          src={getBestThumbnail(artist, 'large')}
          alt={artist.name}
          className="w-48 h-48 rounded-full object-cover bg-secondary shadow-lg"
          onError={(e) => {
            e.currentTarget.src = '/assets/placeholder-music.png';
          }}
        />

        <div className="flex-1">
          <h1 className="text-4xl font-bold text-foreground mb-2">
            {artist.name}
          </h1>
          <p className="text-muted-foreground mb-6">
            {albums.length} {albums.length === 1 ? 'release' : 'releases'}
          </p>

          <div className="flex flex-wrap gap-3">
            <Button
              onClick={handleFollow}
              isLoading={actionLoading}
              variant={isFollowing ? 'secondary' : 'primary'}
            >
              {isFollowing ? t('artist.following') : t('artist.follow')}
            </Button>
          </div>
        </div>
      </div>

      {/* Albums section */}
      {regularAlbums.length > 0 && (
        <section>
          <h2 className="text-2xl font-semibold text-foreground mb-4">
            {t('artist.albums')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {regularAlbums.map((album) => (
              <MediaCard
                key={album.id}
                id={album.id}
                title={album.title}
                thumbnail={getBestThumbnail(album)}
                type="album"
                year={album.year}
                onClick={() => navigate(`/albums/${encodeURIComponent(album.id)}`)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Singles & EPs section */}
      {singles.length > 0 && (
        <section>
          <h2 className="text-2xl font-semibold text-foreground mb-4">
            {t('artist.singles')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {singles.map((album) => (
              <MediaCard
                key={album.id}
                id={album.id}
                title={album.title}
                thumbnail={getBestThumbnail(album)}
                type="album"
                year={album.year}
                onClick={() => navigate(`/albums/${encodeURIComponent(album.id)}`)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Empty state */}
      {albums.length === 0 && (
        <div className="text-center py-12 bg-card rounded-lg border border-border">
          <div className="text-5xl mb-4">💿</div>
          <p className="text-muted-foreground">No albums found for this artist</p>
        </div>
      )}
    </div>
  );
}