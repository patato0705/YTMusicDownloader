// src/pages/Artist.tsx
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { getArtist, followArtist, unfollowArtist } from '../api/artists';
import { getImageUrl } from '../api/media';
import MediaCard from '../components/MediaCard';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { SectionHeader } from '../components/ui/SectionHeader';
import { categorizeAlbums } from '../utils';
import type { Album } from '../types';

export default function Artist(): JSX.Element {
  const { artistId } = useParams<{ artistId: string }>();
  const [artist, setArtist] = useState<any>(null);
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFollowing, setIsFollowing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [artistImageError, setArtistImageError] = useState(false);
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
    setArtistImageError(false);

    try {
      const data = await getArtist(artistId);
      setArtist(data.artist || data);
      
      // Combine albums and singles
      const allAlbums = [
        ...(data.albums || []),
        ...(data.singles || [])
      ];
      
      setAlbums(allAlbums);
      setIsFollowing(data.followed || false);
    } catch (err: any) {
      console.error('Failed to load artist:', err);
      setError(err.message || t('common.error'));
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
      alert(err.message || t('common.error'));
    } finally {
      setActionLoading(false);
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

  if (error || !artist) {
    return (
      <div className="relative min-h-screen">
        {/* Background effects */}
        <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        <div className="relative z-10 space-y-6 py-8">
          <div className="bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl p-6 border border-red-500/20">
            <div className="flex items-center gap-3">
              <span className="text-2xl">⚠️</span>
              <div>
                <h3 className="font-semibold text-red-600 dark:text-red-400 mb-1">
                  {t('common.error')}
                </h3>
                <p className="text-sm text-red-600/80 dark:text-red-400/80">
                  {error || t('artist.notFound')}
                </p>
              </div>
            </div>
          </div>
          <Button onClick={() => navigate('/browse')} variant="primary">
            ← {t('common.back')}
          </Button>
        </div>
      </div>
    );
  }

  const { albums: regularAlbums, singles } = categorizeAlbums(albums);
  const artistThumbnailUrl = getImageUrl(artist.image_local || artist.thumbnail);

  return (
    <div className="relative min-h-screen">
      {/* Background effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
      
      {/* Main content */}
      <div className="relative z-10 space-y-12 pb-12">
        {/* Artist header */}
        <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-8 md:p-12 border border-slate-200/50 dark:border-white/10">
          <div className="flex flex-col md:flex-row gap-8 items-start">
            {/* Artist image */}
            <div className="relative group">
              <img
                src={artistImageError ? '/assets/placeholder-music.png' : artistThumbnailUrl}
                alt={artist.name}
                className="w-48 h-48 md:w-64 md:h-64 rounded-full object-cover bg-slate-200 dark:bg-zinc-800 shadow-2xl ring-4 ring-white/50 dark:ring-white/10 group-hover:scale-105 transition-transform duration-300"
                onError={() => {
                  if (!artistImageError) {
                    setArtistImageError(true);
                  }
                }}
              />
              {/* Glow effect */}
              <div className="absolute inset-0 rounded-full bg-gradient-to-br from-blue-500/20 to-indigo-500/20 dark:from-red-500/20 dark:to-red-700/20 blur-2xl -z-10 group-hover:opacity-75 opacity-0 transition-opacity duration-300" />
            </div>

            {/* Artist info */}
            <div className="flex-1">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full glass mb-4">
                <span className="text-sm text-blue-600 dark:text-red-400 font-medium">
                  🎤 {t('artist.title')}
                </span>
              </div>
              
              <h1 className="text-4xl md:text-5xl font-bold mb-4">
                <span className="text-gradient">{artist.name}</span>
              </h1>
              
              <p className="text-lg text-muted-foreground mb-8">
                {albums.length} {albums.length === 1 ? t('artist.release') : t('artist.releases')}
              </p>

              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={handleFollow}
                  isLoading={actionLoading}
                  variant={isFollowing ? 'secondary' : 'primary'}
                  size="lg"
                >
                  {isFollowing ? (
                    <>
                      <span className="mr-2">✓</span>
                      {t('artist.following')}
                    </>
                  ) : (
                    <>
                      <span className="mr-2">+</span>
                      {t('artist.follow')}
                    </>
                  )}
                </Button>
                
                <Button
                  onClick={() => navigate(-1)}
                  variant="ghost"
                  size="lg"
                >
                  ← {t('common.back')}
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* Albums section */}
        {regularAlbums.length > 0 && (
          <section>
            <SectionHeader>{t('artist.albums')}</SectionHeader>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {regularAlbums.map((album) => (
                <MediaCard
                  key={album.id}
                  id={album.id}
                  title={album.title}
                  thumbnail={getImageUrl(album.image_local || album.thumbnail)}
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
            <SectionHeader>{t('artist.singles')}</SectionHeader>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {singles.map((album) => (
                <MediaCard
                  key={album.id}
                  id={album.id}
                  title={album.title}
                  thumbnail={getImageUrl(album.image_local || album.thumbnail)}
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
          <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-16 border border-slate-200/50 dark:border-white/10 text-center">
            <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-6">
              <span className="text-5xl">💿</span>
            </div>
            <h3 className="text-2xl font-bold mb-3">{t('artist.noAlbums')}</h3>
            <p className="text-muted-foreground">
              {t('artist.noAlbumsDescription')}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}