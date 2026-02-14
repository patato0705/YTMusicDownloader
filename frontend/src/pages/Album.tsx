// src/pages/Album.tsx
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { getAlbum, followAlbum } from '../api/albums';
import { getImageUrl } from '../api/media';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { SectionHeader } from '../components/ui/SectionHeader';
import { formatDuration, getPrimaryArtist } from '../utils';
import type { Track } from '../types';

export default function Album(): JSX.Element {
  const { albumId } = useParams<{ albumId: string }>();
  const [album, setAlbum] = useState<any>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFollowing, setIsFollowing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [imageError, setImageError] = useState(false);
  const navigate = useNavigate();
  const { t } = useI18n();

  useEffect(() => {
    if (albumId) {
      loadAlbum();
    }
  }, [albumId]);

  const loadAlbum = async () => {
    if (!albumId) return;

    setLoading(true);
    setError(null);
    setImageError(false);

    try {
      const data = await getAlbum(albumId);
      setAlbum(data.album || data);
      setTracks(data.tracks || []);
      setIsFollowing(data.followed || false);
    } catch (err: any) {
      console.error('Failed to load album:', err);
      setError(err.message || t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!albumId) return;

    setActionLoading(true);
    try {
      await followAlbum(albumId);
      setIsFollowing(true);
      alert(t('album.downloadQueued'));
    } catch (err: any) {
      console.error('Download failed:', err);
      alert(err.message || t('album.downloadFailed'));
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusStyles = (status?: string) => {
    switch (status) {
      case 'done':
        return 'bg-green-500/20 text-green-600 dark:text-green-400 border-green-500/30';
      case 'failed':
        return 'bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30';
      case 'downloading':
        return 'bg-blue-500/20 text-blue-600 dark:text-blue-400 border-blue-500/30';
      default:
        return 'bg-slate-500/20 text-slate-600 dark:text-slate-400 border-slate-500/30';
    }
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'done':
        return '✓';
      case 'failed':
        return '✗';
      case 'downloading':
        return '↓';
      default:
        return '•';
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

  if (error || !album) {
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
                  {error || t('album.notFound')}
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

  const thumbnailUrl = getImageUrl(album.image_local || album.thumbnail);
  const totalDuration = tracks.reduce((sum, track) => sum + (track.duration_seconds || track.duration || 0), 0);

  return (
    <div className="relative min-h-screen">
      {/* Background effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
      
      {/* Main content */}
      <div className="relative z-10 space-y-12 pb-12">
        {/* Album header */}
        <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-8 md:p-12 border border-slate-200/50 dark:border-white/10">
          <div className="flex flex-col md:flex-row gap-8 items-start">
            {/* Album cover */}
            <div className="relative group">
              <img
                src={imageError ? '/assets/placeholder-music.png' : thumbnailUrl}
                alt={album.title}
                className="w-64 h-64 md:w-80 md:h-80 rounded-2xl object-cover bg-slate-200 dark:bg-zinc-800 shadow-2xl ring-4 ring-white/50 dark:ring-white/10 group-hover:scale-105 transition-transform duration-300"
                onError={() => {
                  if (!imageError) {
                    setImageError(true);
                  }
                }}
              />
              {/* Glow effect */}
              <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-blue-500/20 to-indigo-500/20 dark:from-red-500/20 dark:to-red-700/20 blur-2xl -z-10 group-hover:opacity-75 opacity-0 transition-opacity duration-300" />
            </div>

            {/* Album info */}
            <div className="flex-1">
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full glass mb-4">
                <span className="text-sm text-blue-600 dark:text-red-400 font-medium">
                  💿 {album.type || t('album.album')}
                </span>
              </div>
              
              <h1 className="text-4xl md:text-5xl font-bold mb-4">
                <span className="text-gradient">{album.title}</span>
              </h1>

              {/* Artist link */}
              {album.artist && (
                <button
                  onClick={() => {
                    const artistId = album.artist.id || album.artist_id;
                    if (artistId) {
                      navigate(`/artists/${encodeURIComponent(artistId)}`);
                    }
                  }}
                  className="text-xl text-blue-600 dark:text-red-400 hover:underline mb-4 transition-colors"
                >
                  {album.artist.name || album.artist_name || t('album.unknownArtist')}
                </button>
              )}

              {/* Album metadata */}
              <div className="flex flex-wrap items-center gap-3 text-muted-foreground mb-8">
                {album.year && (
                  <span className="flex items-center gap-2">
                    <span className="text-lg">📅</span>
                    {album.year}
                  </span>
                )}
                <span>•</span>
                <span className="flex items-center gap-2">
                  <span className="text-lg">🎵</span>
                  {tracks.length} {tracks.length === 1 ? t('album.track') : t('album.tracks')}
                </span>
                {totalDuration > 0 && (
                  <>
                    <span>•</span>
                    <span className="flex items-center gap-2">
                      <span className="text-lg">⏱️</span>
                      {formatDuration(totalDuration)}
                    </span>
                  </>
                )}
              </div>

              {/* Action buttons */}
              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={handleDownload}
                  isLoading={actionLoading}
                  variant={isFollowing ? 'secondary' : 'primary'}
                  size="lg"
                  disabled={isFollowing}
                >
                  {isFollowing ? (
                    <>
                      <span className="mr-2">✓</span>
                      {t('album.following')}
                    </>
                  ) : (
                    <>
                      <span className="mr-2">⬇️</span>
                      {t('album.download')}
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

        {/* Tracks list */}
        {tracks.length > 0 ? (
          <section>
            <SectionHeader>{t('album.trackList')}</SectionHeader>
            
            <div className="glass rounded-2xl overflow-hidden border-gradient">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-100/50 dark:bg-white/5 border-b border-slate-200 dark:border-white/10">
                    <tr>
                      <th className="px-4 md:px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider w-12">
                        #
                      </th>
                      <th className="px-4 md:px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        {t('album.title')}
                      </th>
                      <th className="px-4 md:px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider hidden lg:table-cell">
                        {t('album.artist')}
                      </th>
                      <th className="px-4 md:px-6 py-4 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider w-24">
                        {t('album.duration')}
                      </th>
                      <th className="px-4 md:px-6 py-4 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wider w-28">
                        {t('album.status')}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-white/10">
                    {tracks.map((track, index) => (
                      <tr
                        key={track.id}
                        className="hover:bg-slate-50 dark:hover:bg-white/5 transition-colors group"
                      >
                        <td className="px-4 md:px-6 py-4 text-sm text-muted-foreground font-medium">
                          {track.track_number || index + 1}
                        </td>
                        <td className="px-4 md:px-6 py-4">
                          <div className="font-semibold text-foreground group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors">
                            {track.title}
                          </div>
                        </td>
                        <td className="px-4 md:px-6 py-4 text-sm text-muted-foreground hidden lg:table-cell">
                          {getPrimaryArtist(track)}
                        </td>
                        <td className="px-4 md:px-6 py-4 text-sm text-muted-foreground text-right font-mono">
                          {formatDuration(track.duration_seconds || track.duration)}
                        </td>
                        <td className="px-4 md:px-6 py-4 text-center">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border ${getStatusStyles(track.status)}`}
                          >
                            <span>{getStatusIcon(track.status)}</span>
                            <span className="capitalize">{track.status || 'new'}</span>
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : (
          <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-16 border border-slate-200/50 dark:border-white/10 text-center">
            <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-6">
              <span className="text-5xl">🎵</span>
            </div>
            <h3 className="text-2xl font-bold mb-3">{t('album.noTracks')}</h3>
            <p className="text-muted-foreground">
              {t('album.noTracksDescription')}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}