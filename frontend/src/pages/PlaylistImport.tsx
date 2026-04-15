// src/pages/PlaylistImport.tsx
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { getPlaylist } from '../api/playlists';
import { followArtist } from '../api/artists';
import { downloadAlbum } from '../api/albums';
import { getImageUrl } from '../api/media';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Toast } from '../components/ui/Toast';
import { PageHero } from '../components/ui/PageHero';
import { formatDuration, formatDurationLong } from '../utils';
import type { PlaylistTrack } from '../api/playlists';

function TrackThumb({ src, className = '' }: { src?: string | null; className?: string }) {
  const [err, setErr] = React.useState(false);
  const url = getImageUrl(src);
  return (
    <img
      src={err ? '/assets/placeholder-music.png' : url}
      alt=""
      className={`object-cover bg-slate-200 dark:bg-zinc-800 flex-shrink-0 ${className}`}
      onError={() => { if (!err) setErr(true); }}
    />
  );
}

interface UniqueArtist {
  id: string;
  name: string;
  trackCount: number;
  tracks: PlaylistTrack[];
}

interface UniqueAlbum {
  id: string;
  name: string;
  artistId: string | null;
  artistName: string;
  trackCount: number;
  tracks: PlaylistTrack[];
}

function extractPlaylistId(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  try {
    const url = new URL(trimmed);
    const listParam = url.searchParams.get('list');
    if (listParam) return listParam;
  } catch {
    // Not a valid URL - treat as raw playlist ID
  }

  if (/^[A-Za-z0-9_-]+$/.test(trimmed)) return trimmed;
  return null;
}

function extractUniqueArtists(tracks: PlaylistTrack[]): UniqueArtist[] {
  const artistMap = new Map<string, UniqueArtist>();

  for (const track of tracks) {
    for (const artist of track.artists) {
      if (!artist.id || !artist.name) continue;
      const existing = artistMap.get(artist.id);
      if (existing) {
        existing.trackCount++;
        existing.tracks.push(track);
      } else {
        artistMap.set(artist.id, {
          id: artist.id,
          name: artist.name,
          trackCount: 1,
          tracks: [track],
        });
      }
    }
  }

  return Array.from(artistMap.values()).sort((a, b) => b.trackCount - a.trackCount);
}

function extractMainArtists(tracks: PlaylistTrack[]): UniqueArtist[] {
  const artistMap = new Map<string, UniqueArtist>();

  for (const track of tracks) {
    const main = track.artists[0];
    if (!main?.id || !main.name) continue;
    const existing = artistMap.get(main.id);
    if (existing) {
      existing.trackCount++;
      existing.tracks.push(track);
    } else {
      artistMap.set(main.id, {
        id: main.id,
        name: main.name,
        trackCount: 1,
        tracks: [track],
      });
    }
  }

  return Array.from(artistMap.values()).sort((a, b) => b.trackCount - a.trackCount);
}

function extractUniqueAlbums(tracks: PlaylistTrack[]): UniqueAlbum[] {
  const albumMap = new Map<string, UniqueAlbum>();

  for (const track of tracks) {
    if (!track.album?.id || !track.album.name) continue;
    const existing = albumMap.get(track.album.id);
    if (existing) {
      existing.trackCount++;
      existing.tracks.push(track);
    } else {
      const artistId = track.artists[0]?.id || null;
      const artistName = track.artists[0]?.name || '';
      albumMap.set(track.album.id, {
        id: track.album.id,
        name: track.album.name,
        artistId,
        artistName,
        trackCount: 1,
        tracks: [track],
      });
    }
  }

  return Array.from(albumMap.values()).sort((a, b) => b.trackCount - a.trackCount);
}

const VALID_PLAYLIST_FILTERS = ['artists', 'albums', 'tracks'] as const;
type PlaylistFilterType = typeof VALID_PLAYLIST_FILTERS[number];

export default function PlaylistImport(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const filterParam = searchParams.get('filter');
  const activeFilter: PlaylistFilterType = VALID_PLAYLIST_FILTERS.includes(filterParam as PlaylistFilterType)
    ? (filterParam as PlaylistFilterType)
    : 'artists';

  // Local state for responsive typing; URL synced only on playlist load
  const [url, setUrl] = useState(searchParams.get('url') || '');

  const syncUrlToParams = useCallback((value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) {
        next.set('url', value);
      } else {
        next.delete('url');
      }
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const setActiveFilter = useCallback((newFilter: PlaylistFilterType) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('filter', newFilter);
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const [playlistTitle, setPlaylistTitle] = useState<string | null>(null);
  const [playlistThumbnail, setPlaylistThumbnail] = useState<string | null>(null);
  const [playlistAuthor, setPlaylistAuthor] = useState<string | null>(null);
  const [allTracks, setAllTracks] = useState<PlaylistTrack[]>([]);
  const [uniqueArtists, setUniqueArtists] = useState<UniqueArtist[]>([]);
  const [mainArtists, setMainArtists] = useState<UniqueArtist[]>([]);
  const [uniqueAlbums, setUniqueAlbums] = useState<UniqueAlbum[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [followedArtists, setFollowedArtists] = useState<Set<string>>(new Set());
  const [downloadedAlbums, setDownloadedAlbums] = useState<Set<string>>(new Set());
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [bulkProgress, setBulkProgress] = useState<{
    type: 'artists' | 'albums';
    current: number;
    total: number;
  } | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const navigate = useNavigate();
  const { t } = useI18n();

  const hasResults = allTracks.length > 0;
  const isBulkRunning = bulkProgress !== null;

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleLoad = async () => {
    const playlistId = extractPlaylistId(url);
    if (!playlistId) {
      setToast({ message: t('playlist.invalidUrl'), type: 'error' });
      return;
    }

    syncUrlToParams(url);
    setLoading(true);
    setError(null);
    setPlaylistTitle(null);
    setPlaylistThumbnail(null);
    setPlaylistAuthor(null);
    setAllTracks([]);
    setUniqueArtists([]);
    setMainArtists([]);
    setUniqueAlbums([]);
    setFollowedArtists(new Set());
    setDownloadedAlbums(new Set());
    setExpandedIds(new Set());
    setActiveFilter('artists');

    try {
      const playlist = await getPlaylist(playlistId);
      const tracks = playlist.tracks || [];

      setPlaylistTitle(playlist.title || null);
      setPlaylistThumbnail(playlist.thumbnail || null);
      setPlaylistAuthor(playlist.author || null);
      setAllTracks(tracks);
      setUniqueArtists(extractUniqueArtists(tracks));
      setMainArtists(extractMainArtists(tracks));
      setUniqueAlbums(extractUniqueAlbums(tracks));
    } catch (err: any) {
      console.error('Failed to load playlist:', err);
      setError(err.message || t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  // Auto-load playlist when mounting with a URL param (e.g., after back navigation)
  useEffect(() => {
    if (url.trim() && !hasResults && !loading) {
      handleLoad();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFollowArtist = async (artistId: string) => {
    setActionLoadingId(artistId);
    try {
      await followArtist(artistId);
      setFollowedArtists((prev) => new Set(prev).add(artistId));
    } catch (err: any) {
      console.error('Follow failed:', err);
      setToast({ message: err.message || t('common.error'), type: 'error' });
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDownloadAlbum = async (albumId: string) => {
    setActionLoadingId(albumId);
    try {
      await downloadAlbum(albumId);
      setDownloadedAlbums((prev) => new Set(prev).add(albumId));
    } catch (err: any) {
      console.error('Download failed:', err);
      setToast({ message: err.message || t('common.error'), type: 'error' });
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleFollowAll = async () => {
    const toFollow = uniqueArtists.filter((a) => !followedArtists.has(a.id));
    if (toFollow.length === 0) return;

    let succeeded = 0;
    let failed = 0;

    setBulkProgress({ type: 'artists', current: 0, total: toFollow.length });

    for (let i = 0; i < toFollow.length; i++) {
      setBulkProgress({ type: 'artists', current: i + 1, total: toFollow.length });
      try {
        await followArtist(toFollow[i].id);
        setFollowedArtists((prev) => new Set(prev).add(toFollow[i].id));
        succeeded++;
      } catch (err: any) {
        console.error(`Failed to follow ${toFollow[i].name}:`, err);
        failed++;
      }
    }

    setBulkProgress(null);

    if (failed === 0) {
      setToast({ message: t('playlist.followComplete'), type: 'success' });
    } else {
      setToast({
        message: t('playlist.partialSuccess', {
          succeeded: String(succeeded),
          total: String(toFollow.length),
          failed: String(failed),
        }),
        type: 'error',
      });
    }
  };

  const handleFollowMainArtists = async () => {
    const toFollow = mainArtists.filter((a) => !followedArtists.has(a.id));
    if (toFollow.length === 0) return;

    let succeeded = 0;
    let failed = 0;

    setBulkProgress({ type: 'artists', current: 0, total: toFollow.length });

    for (let i = 0; i < toFollow.length; i++) {
      setBulkProgress({ type: 'artists', current: i + 1, total: toFollow.length });
      try {
        await followArtist(toFollow[i].id);
        setFollowedArtists((prev) => new Set(prev).add(toFollow[i].id));
        succeeded++;
      } catch (err: any) {
        console.error(`Failed to follow ${toFollow[i].name}:`, err);
        failed++;
      }
    }

    setBulkProgress(null);

    if (failed === 0) {
      setToast({ message: t('playlist.followComplete'), type: 'success' });
    } else {
      setToast({
        message: t('playlist.partialSuccess', {
          succeeded: String(succeeded),
          total: String(toFollow.length),
          failed: String(failed),
        }),
        type: 'error',
      });
    }
  };

  const handleDownloadAll = async () => {
    const toDownload = uniqueAlbums.filter((a) => !downloadedAlbums.has(a.id));
    if (toDownload.length === 0) return;

    let succeeded = 0;
    let failed = 0;

    setBulkProgress({ type: 'albums', current: 0, total: toDownload.length });

    for (let i = 0; i < toDownload.length; i++) {
      setBulkProgress({ type: 'albums', current: i + 1, total: toDownload.length });
      try {
        await downloadAlbum(toDownload[i].id);
        setDownloadedAlbums((prev) => new Set(prev).add(toDownload[i].id));
        succeeded++;
      } catch (err: any) {
        console.error(`Failed to download ${toDownload[i].name}:`, err);
        failed++;
      }
    }

    setBulkProgress(null);

    if (failed === 0) {
      setToast({ message: t('playlist.downloadComplete'), type: 'success' });
    } else {
      setToast({
        message: t('playlist.partialSuccess', {
          succeeded: String(succeeded),
          total: String(toDownload.length),
          failed: String(failed),
        }),
        type: 'error',
      });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !loading) {
      handleLoad();
    }
  };

  const unfollowedArtistCount = uniqueArtists.filter((a) => !followedArtists.has(a.id)).length;
  const unfollowedMainArtistCount = mainArtists.filter((a) => !followedArtists.has(a.id)).length;
  const undownloadedAlbumCount = uniqueAlbums.filter((a) => !downloadedAlbums.has(a.id)).length;

  const renderArtistLinks = (artists: PlaylistTrack['artists']) => {
    const valid = artists.filter((a) => a.name);
    if (valid.length === 0) return <span>—</span>;
    return (
      <>
        {valid.map((a, i) => (
          <React.Fragment key={a.id || i}>
            {i > 0 && ', '}
            {a.id ? (
              <button
                onClick={(e) => { e.stopPropagation(); navigate(`/artists/${encodeURIComponent(a.id!)}`); }}
                className="hover:text-blue-600 dark:hover:text-red-400 hover:underline transition-colors"
              >
                {a.name}
              </button>
            ) : (
              <span>{a.name}</span>
            )}
          </React.Fragment>
        ))}
      </>
    );
  };

  const renderAlbumLink = (album: PlaylistTrack['album']) => {
    if (!album?.name) return <span>—</span>;
    if (!album.id) return <span>{album.name}</span>;
    return (
      <button
        onClick={(e) => { e.stopPropagation(); navigate(`/albums/${encodeURIComponent(album.id!)}`); }}
        className="hover:text-blue-600 dark:hover:text-red-400 hover:underline transition-colors text-left truncate"
      >
        {album.name}
      </button>
    );
  };

  return (
    <div className="relative min-h-screen">
      {/* Background effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />

      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
      )}

      {/* Main content */}
      <div className="relative z-10 space-y-8 pb-12">
        {/* Hero section */}
        <PageHero
          title={
            <>
              <span className="text-foreground">{t('playlist.title').split(' ')[0]} </span>
              <span className="text-gradient">{t('playlist.title').split(' ').slice(1).join(' ')}</span>
            </>
          }
          subtitle={t('playlist.subtitle')}
        />

        {/* URL input */}
        <div className="flex flex-col sm:flex-row gap-4">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('playlist.urlPlaceholder')}
            disabled={loading || isBulkRunning}
            className="flex-1 px-5 py-3.5 rounded-xl bg-white/60 dark:bg-white/10 border border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-500 transition-all duration-300 disabled:opacity-50"
          />
          <Button
            onClick={handleLoad}
            isLoading={loading}
            disabled={!url.trim() || isBulkRunning}
            variant="primary"
            size="lg"
          >
            {t('playlist.loadPlaylist')}
          </Button>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <Spinner size="lg" className="mx-auto mb-4 text-blue-600 dark:text-red-500" />
              <p className="text-muted-foreground">{t('common.loading')}</p>
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl p-6 border border-red-500/20">
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
        )}

        {/* Results */}
        {!loading && hasResults && (
          <>
            {/* Playlist summary card */}
            <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-6 md:p-8 border-gradient shadow-sm">
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
                <div className="flex items-center gap-4 min-w-0">
                  {/* Playlist thumbnail */}
                  <TrackThumb
                    src={playlistThumbnail}
                    className="w-24 h-24 rounded-2xl shadow-lg flex-shrink-0"
                  />

                  <div className="flex-1 min-w-0">
                    <h2 className="text-2xl font-bold mb-1">
                      <span className="text-gradient">{playlistTitle || 'Playlist'}</span>
                    </h2>
                    {playlistAuthor && (
                      <p className="text-sm text-muted-foreground mb-1">
                        {playlistAuthor}
                      </p>
                    )}
                    <p className="text-muted-foreground">
                      {allTracks.length} {t('playlist.tracksInPlaylist')} · {uniqueArtists.length} {t('playlist.artists').toLowerCase()} · {uniqueAlbums.length} {t('playlist.albums').toLowerCase()} · {formatDurationLong(allTracks.reduce((s, t) => s + (t.duration_seconds || 0), 0))}
                    </p>
                  </div>
                </div>

              </div>
            </div>

            {/* Filter tabs + bulk actions */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-2 glass rounded-2xl p-2">
                {uniqueArtists.length > 0 && (
                  <button
                    onClick={() => setActiveFilter('artists')}
                    className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                      activeFilter === 'artists'
                        ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                        : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                    }`}
                  >
                    {t('playlist.artists')} ({uniqueArtists.length})
                  </button>
                )}
                {uniqueAlbums.length > 0 && (
                  <button
                    onClick={() => setActiveFilter('albums')}
                    className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                      activeFilter === 'albums'
                        ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                        : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                    }`}
                  >
                    {t('playlist.albums')} ({uniqueAlbums.length})
                  </button>
                )}
                <button
                  onClick={() => setActiveFilter('tracks')}
                  className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                    activeFilter === 'tracks'
                      ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                      : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                  }`}
                >
                  {t('playlist.trackView')} ({allTracks.length})
                </button>
              </div>

              {/* Bulk action buttons / progress */}
              {activeFilter === 'artists' && uniqueArtists.length > 0 && (
                <div className="flex items-center gap-2">
                  {bulkProgress && bulkProgress.type === 'artists' ? (
                    <div className="flex items-center gap-3 px-4 py-2 rounded-xl glass">
                      <Spinner size="sm" className="text-blue-600 dark:text-red-500" />
                      <span className="text-sm font-medium text-foreground">
                        {t('playlist.followingProgress', {
                          current: String(bulkProgress.current),
                          total: String(bulkProgress.total),
                        })}
                      </span>
                    </div>
                  ) : (
                    <>
                      <Button
                        onClick={handleFollowAll}
                        disabled={isBulkRunning || unfollowedArtistCount === 0}
                        variant="secondary"
                      >
                        {unfollowedArtistCount === 0
                          ? `✓ ${t('playlist.followAll')}`
                          : `${t('playlist.followAll')} (${unfollowedArtistCount})`}
                      </Button>
                      <Button
                        onClick={handleFollowMainArtists}
                        disabled={isBulkRunning || unfollowedMainArtistCount === 0}
                        variant="primary"
                      >
                        {unfollowedMainArtistCount === 0
                          ? `✓ ${t('playlist.followMainArtists')}`
                          : `${t('playlist.followMainArtists')} (${unfollowedMainArtistCount})`}
                      </Button>
                    </>
                  )}
                </div>
              )}
              {activeFilter === 'albums' && uniqueAlbums.length > 0 && (
                <div className="flex items-center gap-2">
                  {bulkProgress && bulkProgress.type === 'albums' ? (
                    <div className="flex items-center gap-3 px-4 py-2 rounded-xl glass">
                      <Spinner size="sm" className="text-blue-600 dark:text-red-500" />
                      <span className="text-sm font-medium text-foreground">
                        {t('playlist.downloadingProgress', {
                          current: String(bulkProgress.current),
                          total: String(bulkProgress.total),
                        })}
                      </span>
                    </div>
                  ) : (
                    <Button
                      onClick={handleDownloadAll}
                      disabled={isBulkRunning || undownloadedAlbumCount === 0}
                      variant="primary"
                    >
                      {undownloadedAlbumCount === 0
                        ? `✓ ${t('playlist.downloadAll')}`
                        : `${t('playlist.downloadAll')} (${undownloadedAlbumCount})`}
                    </Button>
                  )}
                </div>
              )}
            </div>

            {/* ========== ARTISTS LIST ========== */}
            {activeFilter === 'artists' && (
              <section>
                {uniqueArtists.length > 0 ? (
                  <div className="glass rounded-2xl overflow-hidden border border-slate-200/60 dark:border-white/10 shadow-sm">
                    <div className="divide-y divide-slate-200 dark:divide-white/10">
                      {uniqueArtists.map((artist) => {
                        const isFollowed = followedArtists.has(artist.id);
                        const isLoading = actionLoadingId === artist.id;
                        const isExpanded = expandedIds.has(artist.id);

                        return (
                          <div key={artist.id}>
                            {/* Artist row — whole row toggles expand */}
                            <div
                              onClick={() => toggleExpanded(artist.id)}
                              className="flex items-start sm:items-center gap-4 px-4 md:px-6 py-4 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors cursor-pointer select-none"
                            >
                              {/* Expand chevron */}
                              <svg
                                className={`w-4 h-4 flex-shrink-0 mt-1 sm:mt-0 text-muted-foreground transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                              </svg>

                              {/* Artist info + action */}
                              <div className="flex-1 min-w-0 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                                <div className="flex-1 min-w-0">
                                  <button
                                    onClick={(e) => { e.stopPropagation(); navigate(`/artists/${encodeURIComponent(artist.id)}`); }}
                                    className="font-semibold text-foreground truncate hover:text-blue-600 dark:hover:text-red-400 hover:underline transition-colors text-left block max-w-full"
                                  >
                                    {artist.name}
                                  </button>
                                  <p className="text-sm text-muted-foreground">
                                    {artist.trackCount} {artist.trackCount === 1 ? 'track' : 'tracks'}
                                  </p>
                                </div>

                                {/* Follow button */}
                                <Button
                                  onClick={(e: React.MouseEvent) => { e.stopPropagation(); handleFollowArtist(artist.id); }}
                                  disabled={isFollowed || isLoading || isBulkRunning}
                                  isLoading={isLoading}
                                  variant={isFollowed ? 'secondary' : 'primary'}
                                  size="sm"
                                >
                                  {isFollowed ? `✓ ${t('playlist.followed')}` : t('artist.follow')}
                                </Button>
                              </div>
                            </div>

                            {/* Expanded tracks */}
                            {isExpanded && (
                              <div className="bg-slate-50/50 dark:bg-white/[0.02] border-t border-slate-200/50 dark:border-white/5">
                                {artist.tracks.map((track, idx) => (
                                  <div
                                    key={`${artist.id}-${track.id}-${idx}`}
                                    className="flex items-center gap-3 px-4 md:px-6 pl-12 md:pl-14 py-2 text-sm"
                                  >
                                    <TrackThumb src={track.cover} className="w-8 h-8 rounded" />
                                    <div className="flex-[3] min-w-0">
                                      <p className="truncate text-foreground">{track.title}</p>
                                      {track.album?.name && (
                                        <p className="sm:hidden text-xs text-muted-foreground truncate mt-0.5">
                                          {renderAlbumLink(track.album)}
                                        </p>
                                      )}
                                    </div>
                                    <span className="hidden sm:flex flex-[2] min-w-0 truncate text-muted-foreground">
                                      {renderAlbumLink(track.album)}
                                    </span>
                                    <span className="flex-shrink-0 text-muted-foreground font-mono text-xs">
                                      {track.duration_seconds ? formatDuration(track.duration_seconds) : '—'}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-16 border border-slate-200/50 dark:border-white/10 text-center">
                    <p className="text-muted-foreground">{t('playlist.noArtists')}</p>
                  </div>
                )}
              </section>
            )}

            {/* ========== ALBUMS LIST ========== */}
            {activeFilter === 'albums' && (
              <section>
                {uniqueAlbums.length > 0 ? (
                  <div className="glass rounded-2xl overflow-hidden border border-slate-200/60 dark:border-white/10 shadow-sm">
                    <div className="divide-y divide-slate-200 dark:divide-white/10">
                      {uniqueAlbums.map((album) => {
                        const isDownloaded = downloadedAlbums.has(album.id);
                        const isLoading = actionLoadingId === album.id;
                        const isExpanded = expandedIds.has(album.id);

                        return (
                          <div key={album.id}>
                            {/* Album row — whole row toggles expand */}
                            <div
                              onClick={() => toggleExpanded(album.id)}
                              className="flex items-start sm:items-center gap-4 px-4 md:px-6 py-4 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors cursor-pointer select-none"
                            >
                              {/* Expand chevron */}
                              <svg
                                className={`w-4 h-4 flex-shrink-0 mt-1 sm:mt-0 text-muted-foreground transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                              </svg>

                              {/* Album info + action */}
                              <div className="flex-1 min-w-0 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                                <div className="flex-1 min-w-0">
                                  <button
                                    onClick={(e) => { e.stopPropagation(); navigate(`/albums/${encodeURIComponent(album.id)}`); }}
                                    className="font-semibold text-foreground truncate hover:text-blue-600 dark:hover:text-red-400 hover:underline transition-colors text-left block max-w-full"
                                  >
                                    {album.name}
                                  </button>
                                  <p className="text-sm text-muted-foreground truncate">
                                    {album.artistId ? (
                                      <button
                                        onClick={(e) => { e.stopPropagation(); navigate(`/artists/${encodeURIComponent(album.artistId!)}`); }}
                                        className="hover:text-blue-600 dark:hover:text-red-400 hover:underline transition-colors"
                                      >
                                        {album.artistName}
                                      </button>
                                    ) : (
                                      <span>{album.artistName}</span>
                                    )} · {album.trackCount} {album.trackCount === 1 ? 'track' : 'tracks'}
                                  </p>
                                </div>

                                {/* Download button */}
                                <Button
                                  onClick={(e: React.MouseEvent) => { e.stopPropagation(); handleDownloadAlbum(album.id); }}
                                  disabled={isDownloaded || isLoading || isBulkRunning}
                                  isLoading={isLoading}
                                  variant={isDownloaded ? 'secondary' : 'primary'}
                                  size="sm"
                                >
                                  {isDownloaded ? `✓ ${t('playlist.downloaded')}` : t('album.download')}
                                </Button>
                              </div>
                            </div>

                            {/* Expanded tracks */}
                            {isExpanded && (
                              <div className="bg-slate-50/50 dark:bg-white/[0.02] border-t border-slate-200/50 dark:border-white/5">
                                {album.tracks.map((track, idx) => (
                                  <div
                                    key={`${album.id}-${track.id}-${idx}`}
                                    className="flex items-center gap-3 px-4 md:px-6 pl-12 md:pl-14 py-2 text-sm"
                                  >
                                    <TrackThumb src={track.cover} className="w-8 h-8 rounded" />
                                    <div className="flex-[3] min-w-0">
                                      <p className="truncate text-foreground">{track.title}</p>
                                      <p className="sm:hidden text-xs text-muted-foreground truncate mt-0.5">
                                        {renderArtistLinks(track.artists)}
                                      </p>
                                    </div>
                                    <span className="hidden sm:flex flex-[2] min-w-0 truncate text-muted-foreground">
                                      {renderArtistLinks(track.artists)}
                                    </span>
                                    <span className="flex-shrink-0 text-muted-foreground font-mono text-xs">
                                      {track.duration_seconds ? formatDuration(track.duration_seconds) : '—'}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-16 border border-slate-200/50 dark:border-white/10 text-center">
                    <p className="text-muted-foreground">{t('playlist.noAlbums')}</p>
                  </div>
                )}
              </section>
            )}

            {/* ========== TRACKS LIST ========== */}
            {activeFilter === 'tracks' && (
              <section>
                <div className="glass rounded-2xl overflow-hidden border border-slate-200/60 dark:border-white/10 shadow-sm">
                  {/* Table header */}
                  <div className="hidden sm:flex items-center gap-3 px-4 md:px-6 py-3 bg-slate-100/50 dark:bg-white/5 border-b border-slate-200 dark:border-white/10">
                    <span className="w-8" />
                    <span className="flex-[3] min-w-0 text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('album.title')}</span>
                    <span className="flex-[2] min-w-0 text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('album.artist')}</span>
                    <span className="flex-[2] min-w-0 text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('playlist.albums')}</span>
                    <span className="w-16 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('album.duration')}</span>
                  </div>

                  <div className="divide-y divide-slate-200 dark:divide-white/10">
                    {allTracks.map((track, idx) => (
                      <div
                        key={`${track.id}-${idx}`}
                        className="flex items-center gap-3 px-4 md:px-6 py-2.5 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                      >
                        <TrackThumb src={track.cover} className="w-8 h-8 rounded" />
                        <div className="flex-[3] min-w-0">
                          <p className="font-semibold text-foreground truncate">
                            {track.title}
                          </p>
                          {/* Mobile: show artist + album below title */}
                          <p className="sm:hidden text-xs text-muted-foreground truncate mt-0.5">
                            {renderArtistLinks(track.artists)}
                            {track.album?.name && (
                              <>
                                {' · '}
                                {renderAlbumLink(track.album)}
                              </>
                            )}
                          </p>
                        </div>
                        <span className="hidden sm:flex flex-[2] min-w-0 truncate text-sm text-muted-foreground">
                          {renderArtistLinks(track.artists)}
                        </span>
                        <span className="hidden sm:flex flex-[2] min-w-0 truncate text-sm text-muted-foreground">
                          {renderAlbumLink(track.album)}
                        </span>
                        <span className="w-16 text-right text-sm text-muted-foreground font-mono">
                          {track.duration_seconds ? formatDuration(track.duration_seconds) : '—'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            )}
          </>
        )}

        {/* Empty state - no URL entered yet */}
        {!loading && !hasResults && !error && !playlistTitle && (
          <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-16 border border-slate-200/50 dark:border-white/10 text-center">
            <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-6">
              <span className="text-5xl">📋</span>
            </div>
            <h3 className="text-2xl font-bold mb-3 text-foreground">{t('playlist.title')}</h3>
            <p className="text-muted-foreground max-w-md mx-auto">
              {t('playlist.subtitle')}
            </p>
          </div>
        )}

        {/* Empty playlist state */}
        {!loading && playlistTitle && !hasResults && !error && (
          <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-16 border border-slate-200/50 dark:border-white/10 text-center">
            <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-6">
              <span className="text-5xl">😔</span>
            </div>
            <h3 className="text-2xl font-bold mb-3 text-foreground">{t('playlist.emptyPlaylist')}</h3>
            <p className="text-muted-foreground max-w-md mx-auto">
              {t('playlist.emptyPlaylistDescription')}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
