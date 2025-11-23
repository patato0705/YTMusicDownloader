// src/pages/Album.tsx
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { getAlbum, followAlbum } from '../api/albums';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { formatDuration, getBestThumbnail, getPrimaryArtist } from '../utils';
import type { Track } from '../types';

export default function Album(): JSX.Element {
  const { albumId } = useParams<{ albumId: string }>();
  const [album, setAlbum] = useState<any>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
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

    try {
      const data = await getAlbum(albumId);
      setAlbum(data.album || data);
      setTracks(data.tracks || []);
    } catch (err: any) {
      console.error('Failed to load album:', err);
      setError(err.message || 'Failed to load album');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!albumId) return;

    setActionLoading(true);
    try {
      await followAlbum(albumId);
      alert('Album download queued successfully');
    } catch (err: any) {
      console.error('Download failed:', err);
      alert(err.message || 'Download failed');
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusStyles = (status?: string) => {
    switch (status) {
      case 'done':
        return 'bg-green-500/20 text-green-600 dark:text-green-400';
      case 'failed':
        return 'bg-red-500/20 text-red-600 dark:text-red-400';
      case 'downloading':
        return 'bg-blue-500/20 text-blue-600 dark:text-blue-400';
      default:
        return 'bg-gray-500/20 text-gray-600 dark:text-gray-400';
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

  if (error || !album) {
    return (
      <div className="space-y-4">
        <div className="p-4 bg-red-500/10 border border-red-500 text-red-600 dark:text-red-400 rounded-lg">
          {error || 'Album not found'}
        </div>
        <Button onClick={() => navigate('/browse')}>
          {t('common.back')} to Browse
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Album header */}
      <div className="flex flex-col md:flex-row gap-6 items-start">
        <img
          src={getBestThumbnail(album, 'large')}
          alt={album.title}
          className="w-64 h-64 rounded-lg object-cover bg-secondary shadow-xl"
          onError={(e) => {
            e.currentTarget.src = '/assets/placeholder-music.png';
          }}
        />

        <div className="flex-1">
          <div className="text-sm text-muted-foreground uppercase mb-2">
            {album.type || 'Album'}
          </div>
          <h1 className="text-4xl font-bold text-foreground mb-2">
            {album.title}
          </h1>

          {album.artist && (
            <button
              onClick={() => {
                const artistId = album.artist.id || album.artist_id;
                if (artistId) {
                  navigate(`/artists/${encodeURIComponent(artistId)}`);
                }
              }}
              className="text-lg text-primary hover:underline mb-2"
            >
              {album.artist.name || album.artist_name || 'Unknown Artist'}
            </button>
          )}

          <div className="flex items-center gap-4 text-sm text-muted-foreground mb-6">
            {album.year && <span>{album.year}</span>}
            <span>•</span>
            <span>{tracks.length} {tracks.length === 1 ? 'track' : 'tracks'}</span>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              onClick={handleDownload}
              isLoading={actionLoading}
              variant="primary"
            >
              {t('album.download')}
            </Button>
          </div>
        </div>
      </div>

      {/* Tracks list */}
      {tracks.length > 0 ? (
        <div className="bg-card rounded-lg border border-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-secondary/50 border-b border-border">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider w-12">
                    #
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Title
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider hidden md:table-cell">
                    Artist
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider w-24">
                    Duration
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-24">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {tracks.map((track, index) => (
                  <tr
                    key={track.id}
                    className="hover:bg-accent/50 transition-colors"
                  >
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {track.track_number || index + 1}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{track.title}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground hidden md:table-cell">
                      {getPrimaryArtist(track)}
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground text-right">
                      {formatDuration(track.duration_seconds || track.duration)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`inline-block px-2 py-1 text-xs rounded ${getStatusStyles(
                          track.status
                        )}`}
                      >
                        {track.status || 'new'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="text-center py-12 bg-card rounded-lg border border-border">
          <div className="text-5xl mb-4">🎵</div>
          <p className="text-muted-foreground">No tracks found for this album</p>
        </div>
      )}
    </div>
  );
}