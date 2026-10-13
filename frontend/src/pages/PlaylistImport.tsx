// src/pages/PlaylistImport.tsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { useAuth } from '../contexts/AuthContext';
import { useJobActivity } from '../contexts/JobActivityContext';
import { getPlaylist } from '../api/playlists';
import type { Playlist, PlaylistTrack, SavedPlaylist } from '../api/playlists';
import { followArtist } from '../api/artists';
import { downloadAlbum } from '../api/albums';
import { getImageUrl } from '../api/media';
import { Artwork } from '../components/ui/Artwork';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Toast } from '../components/ui/Toast';
import { PageHero } from '../components/ui/PageHero';
import { FilterTabs } from '../components/ui/FilterTabs';
import type { FilterTab } from '../components/ui/FilterTabs';
import { EmptyState, ErrorBanner, LoadingState } from '../components/ui/PageStatus';
import { PlaylistOptionsDialog } from '../components/playlists/PlaylistOptionsDialog';
import { PlaylistBadges, usePlaylistStats } from '../components/playlists/PlaylistBadges';
import { formatDuration, formatDurationLong, apiErrorMessage, createMemoryCache } from '../utils';
import { useHistoryState } from '../hooks/useHistoryState';

/** Shown in a column with nothing to show */
const NONE = '-';

/** Tracks of the playlist grouped by an artist or an album, most tracks first */
interface TrackGroup {
  id: string;
  name: string;
  tracks: PlaylistTrack[];
}

interface AlbumGroup extends TrackGroup {
  artistId: string | null;
  artistName: string;
}

/**
 * Groups tracks by the keys `keysOf` gives each one (a track can belong to
 * several groups, e.g. one per artist), most tracks first.
 */
function groupTracks<G extends TrackGroup>(
  tracks: PlaylistTrack[],
  keysOf: (track: PlaylistTrack) => Omit<G, 'tracks'>[],
): G[] {
  const groups = new Map<string, G>();
  for (const track of tracks) {
    for (const key of keysOf(track)) {
      const group = groups.get(key.id);
      if (group) group.tracks.push(track);
      else groups.set(key.id, { ...key, tracks: [track] } as G);
    }
  }
  return Array.from(groups.values()).sort((a, b) => b.tracks.length - a.tracks.length);
}

const namedArtist = (artist: PlaylistTrack['artists'][number]): TrackGroup[] =>
  artist?.id && artist.name ? [{ id: artist.id, name: artist.name, tracks: [] }] : [];

function extractPlaylistId(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  try {
    const listParam = new URL(trimmed).searchParams.get('list');
    if (listParam) return listParam;
  } catch {
    // Not a URL: a raw playlist ID
  }

  return /^[A-Za-z0-9_-]+$/.test(trimmed) ? trimmed : null;
}

/** What the page shows of a playlist */
interface PlaylistView {
  id: string;
  title: string | null;
  thumbnail: string | null;
  author: string | null;
  tracks: PlaylistTrack[];
  /** Every artist named on a track */
  artists: TrackGroup[];
  /** The first artist of each track, what "Follow main artists" follows */
  mainArtistIds: Set<string>;
  albums: AlbumGroup[];
}

function playlistView(id: string, playlist: Playlist): PlaylistView {
  const tracks = playlist.tracks || [];
  return {
    id,
    title: playlist.title || null,
    thumbnail: playlist.thumbnail || null,
    author: playlist.author || null,
    tracks,
    artists: groupTracks<TrackGroup>(tracks, (track) => track.artists.flatMap(namedArtist)),
    mainArtistIds: new Set(tracks.flatMap((track) => namedArtist(track.artists[0]).map((a) => a.id))),
    albums: groupTracks<AlbumGroup>(tracks, (track) =>
      track.album?.id && track.album.name
        ? [{
            id: track.album.id,
            name: track.album.name,
            artistId: track.artists[0]?.id || null,
            artistName: track.artists[0]?.name || '',
          }]
        : []
    ),
  };
}

/**
 * Playlists by id: coming back to one shows it right away instead of fetching
 * it again from YouTube Music (slow for long ones), then refreshes it
 */
const playlistCache = createMemoryCache<Playlist>(10);

const VALID_PLAYLIST_FILTERS = ['artists', 'albums', 'tracks'] as const;
type PlaylistFilterType = typeof VALID_PLAYLIST_FILTERS[number];

function TrackThumb({ track }: { track: PlaylistTrack }) {
  return (
    <Artwork
      src={getImageUrl(track.cover)}
      name={track.album?.name || track.title}
      seed={track.album?.id || track.id}
      className="w-8 h-8 rounded bg-slate-200 dark:bg-zinc-800 flex-shrink-0"
    />
  );
}

interface ExpandableRowProps {
  expanded: boolean;
  onToggle: () => void;
  /** Name, details, badges */
  children: React.ReactNode;
  /** Follow or download button, on the right */
  action: React.ReactNode;
  /** Shown under the row while expanded */
  tracks: React.ReactNode;
}

/** An artist or album of the playlist: the whole row opens its tracks */
function ExpandableRow({ expanded, onToggle, children, action, tracks }: ExpandableRowProps) {
  return (
    <div>
      <div
        onClick={onToggle}
        className="flex items-start sm:items-center gap-4 px-4 md:px-6 py-4 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors cursor-pointer select-none"
      >
        <svg
          className={`w-4 h-4 flex-shrink-0 mt-1 sm:mt-0 text-muted-foreground transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <div className="flex-1 min-w-0 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
          <div className="flex-1 min-w-0">{children}</div>
          {action}
        </div>
      </div>
      {expanded && (
        <div className="bg-slate-50/50 dark:bg-white/[0.02] border-t border-slate-200/50 dark:border-white/5">
          {tracks}
        </div>
      )}
    </div>
  );
}

export default function PlaylistImport(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const filterParam = searchParams.get('filter');
  const activeFilter: PlaylistFilterType = VALID_PLAYLIST_FILTERS.includes(filterParam as PlaylistFilterType)
    ? (filterParam as PlaylistFilterType)
    : 'artists';

  // Local state for responsive typing; URL synced only on playlist load
  const [url, setUrl] = useState(searchParams.get('url') || '');

  // A new playlist opens on the artists tab. Both params in one update:
  // `prev` is the URL of the last render, so a second setSearchParams in the
  // same handler would drop the first one's change.
  const syncUrlToParams = useCallback((value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) {
        next.set('url', value);
      } else {
        next.delete('url');
      }
      next.set('filter', 'artists');
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

  // The playlist in the URL, when it's cached: rendered on the first frame, so
  // the back button lands where the page was scrolled
  const [restored] = useState(() => {
    const id = extractPlaylistId(searchParams.get('url') || '');
    const playlist = id ? playlistCache.get(id) : undefined;
    return id && playlist ? { view: playlistView(id, playlist), playlist } : null;
  });

  const [view, setView] = useState<PlaylistView | null>(restored?.view ?? null);
  // How it's added to the library (null: it isn't), and what's followed or
  // downloaded already: changed by the actions on this page
  const [saved, setSaved] = useState<SavedPlaylist | null>(restored?.playlist.saved ?? null);
  const [followedArtists, setFollowedArtists] = useState<Set<string>>(() => new Set(restored?.playlist.followed_artists));
  const [downloadedAlbums, setDownloadedAlbums] = useState<Set<string>>(() => new Set(restored?.playlist.downloaded_albums));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [bulkProgress, setBulkProgress] = useState<{
    type: 'artists' | 'albums';
    current: number;
    total: number;
  } | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [expandedIds, setExpandedIds] = useHistoryState<Set<string>>('expanded', () => new Set());
  // Only the latest fetch is shown: a refresh still running when another
  // playlist is loaded is dropped
  const latestRequestRef = useRef(0);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const playlistStats = usePlaylistStats();

  const navigate = useNavigate();
  const { t } = useI18n();
  const { user } = useAuth();
  const { refresh: refreshJobs } = useJobActivity();
  // Visitors are read-only: follow/download are member+ actions on the backend
  const canModify = user?.role === 'administrator' || user?.role === 'member';

  const isBulkRunning = bulkProgress !== null;

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const showPlaylist = (playlistId: string, playlist: Playlist) => {
    setView(playlistView(playlistId, playlist));
    setSaved(playlist.saved ?? null);
    setFollowedArtists(new Set(playlist.followed_artists));
    setDownloadedAlbums(new Set(playlist.downloaded_albums));
  };

  // `refresh`: the playlist is already on screen (from the cache) and stays
  // there, quietly updated, through the fetch and through an error
  const fetchPlaylist = async (playlistId: string, refresh: boolean) => {
    const request = ++latestRequestRef.current;
    if (!refresh) {
      setLoading(true);
      setError(null);
    }

    try {
      const playlist = await getPlaylist(playlistId);
      playlistCache.set(playlistId, playlist);
      if (request === latestRequestRef.current) showPlaylist(playlistId, playlist);
    } catch (err: any) {
      console.error('Failed to load playlist:', err);
      if (!refresh && request === latestRequestRef.current) setError(apiErrorMessage(err, t, t('common.error')));
    } finally {
      if (!refresh && request === latestRequestRef.current) setLoading(false);
    }
  };

  const handleLoad = () => {
    const playlistId = extractPlaylistId(url);
    if (!playlistId) {
      setToast({ message: t('playlist.invalidUrl'), type: 'error' });
      return;
    }

    syncUrlToParams(url);
    setView(null);
    setSaved(null);
    setFollowedArtists(new Set());
    setDownloadedAlbums(new Set());
    setExpandedIds(new Set());
    fetchPlaylist(playlistId, false);
  };

  // Mounting with a playlist in the URL (back button, link from the library):
  // fetched, or refreshed when it came from the cache. The tab and the open
  // rows stay as they were.
  useEffect(() => {
    const playlistId = extractPlaylistId(url);
    if (playlistId) fetchPlaylist(playlistId, restored !== null);
  }, []);

  // Follows, downloads and library changes made here are kept in the cached
  // copy, so coming back doesn't show them undone until the refresh lands
  const loadedId = view?.id;
  useEffect(() => {
    if (!loadedId) return;
    const cached = playlistCache.get(loadedId);
    if (!cached) return;
    playlistCache.set(loadedId, {
      ...cached,
      saved,
      followed_artists: [...followedArtists],
      downloaded_albums: [...downloadedAlbums],
    });
  }, [loadedId, saved, followedArtists, downloadedAlbums]);

  const markFollowed = (id: string) => setFollowedArtists((prev) => new Set(prev).add(id));
  const markDownloaded = (id: string) => setDownloadedAlbums((prev) => new Set(prev).add(id));
  const follow = (artist: TrackGroup) => followArtist(artist.id, artist.name);
  const download = async (album: TrackGroup) => { await downloadAlbum(album.id); };

  const runAction = async (item: TrackGroup, action: (item: TrackGroup) => Promise<void>, markDone: (id: string) => void) => {
    setActionLoadingId(item.id);
    try {
      await action(item);
      markDone(item.id);
      refreshJobs();
    } catch (err: any) {
      console.error('Action failed:', err);
      setToast({ message: apiErrorMessage(err, t, t('common.error')), type: 'error' });
    } finally {
      setActionLoadingId(null);
    }
  };

  // Follow or download every remaining item, one at a time
  const runBulkAction = async (
    items: TrackGroup[],
    type: 'artists' | 'albums',
    action: (item: TrackGroup) => Promise<void>,
    markDone: (id: string) => void,
    successMessageKey: string,
  ) => {
    if (items.length === 0) return;

    let failed = 0;
    for (let i = 0; i < items.length; i++) {
      setBulkProgress({ type, current: i + 1, total: items.length });
      try {
        await action(items[i]);
        markDone(items[i].id);
      } catch (err: any) {
        console.error(`Bulk ${type} action failed for ${items[i].name}:`, err);
        failed++;
      }
    }

    setBulkProgress(null);
    refreshJobs();
    setToast(failed === 0
      ? { message: t(successMessageKey), type: 'success' }
      : {
          message: t('playlist.partialSuccess', { succeeded: items.length - failed, total: items.length, failed }),
          type: 'error',
        });
  };

  const tracks = view?.tracks ?? [];
  const artists = view?.artists ?? [];
  const albums = view?.albums ?? [];
  const mainArtists = artists.filter((a) => view?.mainArtistIds.has(a.id));
  const unfollowedArtists = artists.filter((a) => !followedArtists.has(a.id));
  const unfollowedMainArtists = mainArtists.filter((a) => !followedArtists.has(a.id));
  const undownloadedAlbums = albums.filter((a) => !downloadedAlbums.has(a.id));
  // Songs with no album (music videos, uploads): no import brings them in
  const noAlbumCount = tracks.filter((track) => !track.album?.id).length;

  const linkClass = 'hover:text-blue-600 dark:hover:text-red-400 hover:underline transition-colors text-left';
  const goTo = (path: string) => (e: React.MouseEvent) => {
    e.stopPropagation();
    navigate(path);
  };

  const artistLinks = (trackArtists: PlaylistTrack['artists']) => {
    const named = trackArtists.filter((a) => a.name);
    if (named.length === 0) return <span>{NONE}</span>;
    return named.map((a, i) => (
      <React.Fragment key={a.id || i}>
        {i > 0 && ', '}
        {a.id ? (
          <button onClick={goTo(`/artists/${encodeURIComponent(a.id)}`)} className={linkClass}>{a.name}</button>
        ) : (
          <span>{a.name}</span>
        )}
      </React.Fragment>
    ));
  };

  const albumLink = (album: PlaylistTrack['album']) => {
    if (!album?.name) return <span>{NONE}</span>;
    if (!album.id) return <span>{album.name}</span>;
    return (
      <button onClick={goTo(`/albums/${encodeURIComponent(album.id)}`)} className={`${linkClass} truncate`}>
        {album.name}
      </button>
    );
  };

  const duration = (track: PlaylistTrack) => (track.duration_seconds ? formatDuration(track.duration_seconds) : NONE);

  /** The tracks under an expanded artist (with their album) or album (with their artists) */
  const groupTrackList = (groupId: string, groupTracks: PlaylistTrack[], detail: (track: PlaylistTrack) => React.ReactNode) =>
    groupTracks.map((track, idx) => (
      <div key={`${groupId}-${track.id}-${idx}`} className="flex items-center gap-3 px-4 md:px-6 pl-12 md:pl-14 py-2 text-sm">
        <TrackThumb track={track} />
        <div className="flex-[3] min-w-0">
          <p className="truncate text-foreground">{track.title}</p>
          <p className="sm:hidden text-xs text-muted-foreground truncate mt-0.5">{detail(track)}</p>
        </div>
        <span className="hidden sm:flex flex-[2] min-w-0 truncate text-muted-foreground">{detail(track)}</span>
        <span className="flex-shrink-0 text-muted-foreground font-mono text-xs">{duration(track)}</span>
      </div>
    ));

  const actionButton = (done: boolean, id: string, doneLabel: string, label: string, onClick: () => void) =>
    // Visitors only see the inert "done" state
    (canModify || done) && (
      <Button
        onClick={(e: React.MouseEvent) => { e.stopPropagation(); onClick(); }}
        disabled={done || actionLoadingId === id || isBulkRunning}
        isLoading={actionLoadingId === id}
        variant={done ? 'secondary' : 'primary'}
        size="sm"
      >
        {done ? `✓ ${doneLabel}` : label}
      </Button>
    );

  const bulkButton = (label: string, remaining: number, onClick: () => void, variant: 'primary' | 'secondary') => (
    <Button onClick={onClick} disabled={isBulkRunning || remaining === 0} variant={variant}>
      {remaining === 0 ? `✓ ${label}` : `${label} (${remaining})`}
    </Button>
  );

  const tabs: FilterTab<PlaylistFilterType>[] = [
    ...(artists.length > 0 ? [{ id: 'artists' as const, label: `${t('playlist.artists')} (${artists.length})` }] : []),
    ...(albums.length > 0 ? [{ id: 'albums' as const, label: `${t('playlist.albums')} (${albums.length})` }] : []),
    { id: 'tracks', label: `${t('playlist.trackView')} (${tracks.length})` },
  ];

  const listClass = 'glass rounded-2xl overflow-hidden shadow-sm';

  return (
    <div className="space-y-8 pb-12">
      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
      )}

      <PageHero
        title={
          <>
            <span className="text-foreground">{t('playlist.heroImport')} </span>
            <span className="text-gradient">{t('playlist.heroPlaylist')}</span>
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
          onKeyDown={(e) => { if (e.key === 'Enter' && !loading) handleLoad(); }}
          placeholder={t('playlist.urlPlaceholder')}
          aria-label={t('playlist.urlPlaceholder')}
          disabled={loading || isBulkRunning}
          className="flex-1 px-5 py-3.5 rounded-xl bg-white/60 dark:bg-white/10 border border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-500 transition-all duration-300 disabled:opacity-50"
        />
        <Button onClick={handleLoad} isLoading={loading} disabled={!url.trim() || isBulkRunning} variant="primary" size="lg">
          {t('playlist.loadPlaylist')}
        </Button>
      </div>

      {loading && <LoadingState className="py-12" />}

      {error && <ErrorBanner title={t('common.error')}>{error}</ErrorBanner>}

      {!loading && view && tracks.length > 0 && (
        <>
          {/* Playlist summary */}
          <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-6 md:p-8 border-gradient shadow-sm">
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div className="flex items-center gap-4 min-w-0">
                <Artwork
                  src={getImageUrl(view.thumbnail)}
                  name={view.title}
                  className="w-24 h-24 rounded-2xl shadow-lg bg-slate-200 dark:bg-zinc-800 flex-shrink-0"
                />

                <div className="flex-1 min-w-0">
                  <h2 className="text-2xl font-bold mb-1">
                    <span className="text-gradient">{view.title || t('playlist.untitled')}</span>
                  </h2>
                  {view.author && <p className="text-sm text-muted-foreground mb-1">{view.author}</p>}
                  <p className="text-muted-foreground">
                    {[
                      t('playlist.summary.tracks', { count: tracks.length }),
                      t('playlist.summary.artists', { count: artists.length }),
                      t('playlist.summary.albums', { count: albums.length }),
                      formatDurationLong(tracks.reduce((sum, track) => sum + (track.duration_seconds || 0), 0)),
                    ].join(' · ')}
                  </p>
                  {noAlbumCount > 0 && (
                    <p className="text-xs text-muted-foreground mt-1">
                      {t('playlist.noAlbumNote', { count: noAlbumCount })}
                    </p>
                  )}
                </div>
              </div>

              {/* In the library: how it's added; otherwise the button to add it */}
              <div className="sm:ml-auto flex flex-col items-start sm:items-end gap-2 flex-shrink-0">
                {saved ? (
                  <>
                    <PlaylistBadges saved={saved} className="sm:justify-end" />
                    <p className="text-xs text-muted-foreground">{playlistStats(saved)}</p>
                    {canModify && (
                      <Button variant="secondary" size="sm" onClick={() => setOptionsOpen(true)} disabled={isBulkRunning}>
                        {t('playlist.options.editButton')}
                      </Button>
                    )}
                  </>
                ) : canModify ? (
                  <>
                    <Button variant="primary" onClick={() => setOptionsOpen(true)} disabled={isBulkRunning}>
                      {t('playlist.options.addButton')}
                    </Button>
                    <p className="text-xs text-muted-foreground max-w-[16rem] sm:text-right">{t('playlist.options.addHint')}</p>
                  </>
                ) : null}
              </div>
            </div>
          </div>

          {optionsOpen && (
            <PlaylistOptionsDialog
              playlistId={view.id}
              playlistTitle={view.title || view.id}
              saved={saved}
              onClose={() => setOptionsOpen(false)}
              onSaved={(result) => {
                setToast({ message: t(saved ? 'playlist.options.saved' : 'playlist.options.added'), type: 'success' });
                setSaved(result);
                refreshJobs();
              }}
              onRemoved={() => {
                setToast({ message: t('playlist.options.removed'), type: 'success' });
                setSaved(null);
              }}
            />
          )}

          {/* Filter tabs and bulk actions */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <FilterTabs tabs={tabs} active={activeFilter} onChange={setActiveFilter} />

            {canModify && ((activeFilter === 'artists' && artists.length > 0) || (activeFilter === 'albums' && albums.length > 0)) && (
              <div className="flex items-center gap-2">
                {bulkProgress?.type === (activeFilter === 'artists' ? 'artists' : 'albums') ? (
                  <div className="flex items-center gap-3 px-4 py-2 rounded-xl glass">
                    <Spinner size="sm" className="text-blue-600 dark:text-red-500" />
                    <span className="text-sm font-medium text-foreground">
                      {t(activeFilter === 'artists' ? 'playlist.followingProgress' : 'playlist.downloadingProgress', {
                        current: bulkProgress.current,
                        total: bulkProgress.total,
                      })}
                    </span>
                  </div>
                ) : activeFilter === 'artists' ? (
                  <>
                    {bulkButton(t('playlist.followAll'), unfollowedArtists.length, () =>
                      runBulkAction(unfollowedArtists, 'artists', follow, markFollowed, 'playlist.followComplete'), 'secondary')}
                    {bulkButton(t('playlist.followMainArtists'), unfollowedMainArtists.length, () =>
                      runBulkAction(unfollowedMainArtists, 'artists', follow, markFollowed, 'playlist.followComplete'), 'primary')}
                  </>
                ) : (
                  bulkButton(t('playlist.downloadAll'), undownloadedAlbums.length, () =>
                    runBulkAction(undownloadedAlbums, 'albums', download, markDownloaded, 'playlist.downloadComplete'), 'primary')
                )}
              </div>
            )}
          </div>

          {activeFilter === 'artists' && (
            artists.length > 0 ? (
              <div className={listClass}>
                <div className="divide-y divide-slate-200 dark:divide-white/10">
                  {artists.map((artist) => {
                    const isMain = view.mainArtistIds.has(artist.id);
                    return (
                      <ExpandableRow
                        key={artist.id}
                        expanded={expandedIds.has(artist.id)}
                        onToggle={() => toggleExpanded(artist.id)}
                        action={actionButton(
                          followedArtists.has(artist.id), artist.id, t('playlist.followed'), t('artist.follow'),
                          () => runAction(artist, follow, markFollowed),
                        )}
                        tracks={groupTrackList(artist.id, artist.tracks, (track) => albumLink(track.album))}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <button
                            onClick={goTo(`/artists/${encodeURIComponent(artist.id)}`)}
                            className={`font-semibold text-foreground truncate min-w-0 ${linkClass}`}
                          >
                            {artist.name}
                          </button>
                          {/* Same rule as "Follow main artists": first artist on at least one track */}
                          <span
                            className={`flex-shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border ${
                              isMain
                                ? 'bg-blue-500/10 text-blue-700 border-blue-500/30 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/30'
                                : 'border-slate-300/70 dark:border-white/10 text-muted-foreground'
                            }`}
                          >
                            {t(isMain ? 'playlist.mainArtist' : 'playlist.secondaryArtist')}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground">{t('playlist.trackCount', { count: artist.tracks.length })}</p>
                      </ExpandableRow>
                    );
                  })}
                </div>
              </div>
            ) : (
              <EmptyState icon="🎤" title={t('playlist.noArtists')} />
            )
          )}

          {activeFilter === 'albums' && (
            albums.length > 0 ? (
              <div className={listClass}>
                <div className="divide-y divide-slate-200 dark:divide-white/10">
                  {albums.map((album) => (
                    <ExpandableRow
                      key={album.id}
                      expanded={expandedIds.has(album.id)}
                      onToggle={() => toggleExpanded(album.id)}
                      action={actionButton(
                        downloadedAlbums.has(album.id), album.id, t('playlist.downloaded'), t('album.download'),
                        () => runAction(album, download, markDownloaded),
                      )}
                      tracks={groupTrackList(album.id, album.tracks, (track) => artistLinks(track.artists))}
                    >
                      <button
                        onClick={goTo(`/albums/${encodeURIComponent(album.id)}`)}
                        className={`font-semibold text-foreground truncate block max-w-full ${linkClass}`}
                      >
                        {album.name}
                      </button>
                      <p className="text-sm text-muted-foreground truncate">
                        {album.artistId ? (
                          <button onClick={goTo(`/artists/${encodeURIComponent(album.artistId)}`)} className={linkClass}>
                            {album.artistName}
                          </button>
                        ) : (
                          <span>{album.artistName}</span>
                        )}
                        {' · '}
                        {t('playlist.trackCount', { count: album.tracks.length })}
                      </p>
                    </ExpandableRow>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyState icon="💿" title={t('playlist.noAlbums')} />
            )
          )}

          {activeFilter === 'tracks' && (
            <div className={listClass}>
              <div className="hidden sm:flex items-center gap-3 px-4 md:px-6 py-3 bg-slate-100/50 dark:bg-white/5 border-b border-slate-200 dark:border-white/10 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                <span className="w-8" />
                <span className="flex-[3] min-w-0">{t('album.title')}</span>
                <span className="flex-[2] min-w-0">{t('album.artist')}</span>
                <span className="flex-[2] min-w-0">{t('album.album')}</span>
                <span className="w-16 text-right">{t('album.duration')}</span>
              </div>

              <div className="divide-y divide-slate-200 dark:divide-white/10">
                {tracks.map((track, idx) => (
                  <div
                    key={`${track.id}-${idx}`}
                    className="flex items-center gap-3 px-4 md:px-6 py-2.5 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors"
                  >
                    <TrackThumb track={track} />
                    <div className="flex-[3] min-w-0">
                      <p className="font-semibold text-foreground truncate">{track.title}</p>
                      {/* Phones: artist and album under the title */}
                      <p className="sm:hidden text-xs text-muted-foreground truncate mt-0.5">
                        {artistLinks(track.artists)}
                        {track.album?.name && <>{' · '}{albumLink(track.album)}</>}
                      </p>
                    </div>
                    <span className="hidden sm:flex flex-[2] min-w-0 truncate text-sm text-muted-foreground">
                      {artistLinks(track.artists)}
                    </span>
                    <span className="hidden sm:flex flex-[2] min-w-0 truncate text-sm text-muted-foreground">
                      {albumLink(track.album)}
                    </span>
                    <span className="w-16 text-right text-sm text-muted-foreground font-mono">{duration(track)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Nothing loaded yet */}
      {!loading && !view && !error && (
        <EmptyState icon="📋" title={t('playlist.title')}>
          <p>{t('playlist.subtitle')}</p>
        </EmptyState>
      )}

      {!loading && view && tracks.length === 0 && (
        <EmptyState icon="😔" title={t('playlist.emptyPlaylist')}>
          <p>{t('playlist.emptyPlaylistDescription')}</p>
        </EmptyState>
      )}
    </div>
  );
}
