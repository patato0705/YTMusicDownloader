// src/pages/Library.tsx
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { getLibraryArtists, getLibraryAlbums, getLibraryStats, searchLibraryTracks } from '../api/library';
import { exportLibrary, downloadJson, exportFilename } from '../api/export';
import type { LibraryTrack } from '../api/library';
import { getImageUrl } from '../api/media';
import MediaCard from '../components/MediaCard';
import { MediaList, MediaRow } from '../components/MediaList';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { StatCard } from '../components/ui/StatCard';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import { SearchInput } from '../components/ui/SearchInput';
import { ViewToggle, type ViewMode } from '../components/ui/ViewToggle';
import { formatNumber, parseApiError, getAlbumStatus, getArtistStatus } from '../utils';
import { useJobActivity } from '../contexts/JobActivityContext';
import { useDebounce } from '../hooks/useDebounce';
import { useProgressiveList } from '../hooks/useProgressiveList';
import type { Artist } from '../types';

// Icon components
const ArtistsIcon = () => <span className="text-2xl">🎤</span>;
const AlbumsIcon = () => <span className="text-2xl">💿</span>;
const TracksIcon = () => <span className="text-2xl">🎵</span>;
const ActivityIcon = () => <span className="text-2xl">⚡</span>;
const LibraryIcon = () => <span className="text-2xl">📚</span>;
const SearchIcon = () => <span className="text-2xl">🔍</span>;

const VIEW_STORAGE_KEY = 'library.view';
const TRACK_SEARCH_DEBOUNCE_MS = 250;
/** Shortest gap between two refreshes triggered by the job queue */
const REFRESH_MIN_GAP_MS = 5000;
/** Cards mounted per scroll step - a multiple of every grid column count (2-5) */
const PAGE_SIZE = 60;

/** Tracks matching the search, grouped by the album / artist they belong to */
interface TrackMatches {
  /** The query these results answer - lets the UI tell fresh results from stale ones */
  query: string;
  byAlbum: Map<string, LibraryTrack[]>;
  byArtist: Map<string, LibraryTrack[]>;
}

const NO_TRACK_MATCHES: TrackMatches = { query: '', byAlbum: new Map(), byArtist: new Map() };

function groupTrackMatches(query: string, tracks: LibraryTrack[]): TrackMatches {
  const byAlbum = new Map<string, LibraryTrack[]>();
  const byArtist = new Map<string, LibraryTrack[]>();

  for (const track of tracks) {
    const albumId = track.album?.id;
    const artistId = track.artist?.id;
    if (albumId) byAlbum.set(albumId, [...(byAlbum.get(albumId) || []), track]);
    if (artistId) byArtist.set(artistId, [...(byArtist.get(artistId) || []), track]);
  }

  return { query, byAlbum, byArtist };
}

function loadViewMode(): ViewMode {
  try {
    return localStorage.getItem(VIEW_STORAGE_KEY) === 'list' ? 'list' : 'grid';
  } catch {
    return 'grid';
  }
}

export default function Library(): JSX.Element {
  const [artists, setArtists] = useState<Artist[]>([]);
  const [albums, setAlbums] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'all' | 'artists' | 'albums'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [trackMatches, setTrackMatches] = useState<TrackMatches>(NO_TRACK_MATCHES);
  const [viewMode, setViewMode] = useState<ViewMode>(loadViewMode);
  const [exporting, setExporting] = useState(false);
  const debouncedQuery = useDebounce(searchQuery.trim(), TRACK_SEARCH_DEBOUNCE_MS);
  const navigate = useNavigate();
  const { t } = useI18n();
  const { revision } = useJobActivity();

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, viewMode);
    } catch {
      // Storage unavailable - the choice just won't survive a reload
    }
  }, [viewMode]);

  // Kept in a ref so the effects below don't refire on it
  const fetchRef = useRef({ loaded: false, inFlight: false, queued: false, lastStartedAt: 0, unmounted: false });

  const loadLibrary = useCallback(async () => {
    const state = fetchRef.current;
    if (state.unmounted) return;
    if (state.inFlight) {
      // Folded into one follow-up once the current fetch lands
      state.queued = true;
      return;
    }

    state.inFlight = true;
    state.lastStartedAt = Date.now();

    try {
      const [artistsResponse, albumsResponse, statsResponse] = await Promise.all([
        getLibraryArtists(),
        getLibraryAlbums(),
        getLibraryStats(),
      ]);

      if (state.unmounted) return;
      setArtists((artistsResponse as any)?.artists || artistsResponse || []);
      setAlbums((albumsResponse as any)?.albums || albumsResponse || []);
      setStats(statsResponse || {});
      setError(null);
      state.loaded = true;
    } catch (err: any) {
      console.error('Failed to load library:', err);
      // A failed background refresh keeps what's on screen
      if (!state.unmounted && !state.loaded) setError(parseApiError(err, 'Failed to load library'));
    } finally {
      state.inFlight = false;
      if (!state.unmounted) setLoading(false);
      if (state.queued) {
        state.queued = false;
        window.setTimeout(loadLibrary, Math.max(0, state.lastStartedAt + REFRESH_MIN_GAP_MS - Date.now()));
      }
    }
  }, []);

  useEffect(() => {
    const state = fetchRef.current;
    state.unmounted = false;
    return () => { state.unmounted = true; };
  }, []);

  // Load on mount, then refresh whenever the job queue moves, so status
  // badges follow downloads started from anywhere - including ones this page
  // hasn't heard of yet. Artists are refreshed too: their badge comes from
  // their track counts.
  // While downloads run the queue moves every few seconds, so refreshes are
  // spaced at least REFRESH_MIN_GAP_MS apart and the bumps in between are
  // batched into the next one.
  useEffect(() => {
    const { lastStartedAt } = fetchRef.current;
    const delay = lastStartedAt ? Math.max(0, lastStartedAt + REFRESH_MIN_GAP_MS - Date.now()) : 0;
    const timer = window.setTimeout(loadLibrary, delay);
    return () => window.clearTimeout(timer);
  }, [revision, loadLibrary]);

  // Tracks aren't listed on this page, so a title-only search goes to the
  // server and the matching albums / artists are surfaced instead.
  useEffect(() => {
    if (!debouncedQuery) {
      setTrackMatches(NO_TRACK_MATCHES);
      return;
    }

    let cancelled = false;

    searchLibraryTracks(debouncedQuery)
      .then((response) => {
        if (!cancelled) setTrackMatches(groupTrackMatches(debouncedQuery, response?.tracks || []));
      })
      .catch((err) => {
        console.error('Failed to search library tracks:', err);
        if (!cancelled) setTrackMatches({ ...NO_TRACK_MATCHES, query: debouncedQuery });
      });

    return () => { cancelled = true; };
  }, [debouncedQuery, revision]);

  // Results are only shown once they answer the current input, so a query the
  // user has moved on from never leaks stale hints. A refetch triggered by the
  // job poller keeps the previous results on screen until the new ones land,
  // instead of blanking them on every tick.
  const trackMatchesReady = trackMatches.query === searchQuery.trim();
  const albumTrackMatches = trackMatchesReady ? trackMatches.byAlbum : NO_TRACK_MATCHES.byAlbum;
  const artistTrackMatches = trackMatchesReady ? trackMatches.byArtist : NO_TRACK_MATCHES.byArtist;

  const albumTitleById = useMemo(
    () => new Map<string, string>(albums.map((album) => [album.id, album.title])),
    [albums]
  );

  // An artist's badge depends on its albums - grouped once instead of
  // scanning every album for every artist card
  const albumsByArtist = useMemo(() => {
    const byArtist = new Map<string, any[]>();
    for (const album of albums) {
      const artistId = album.artist?.id ?? album.artist_id;
      if (!artistId) continue;
      const artistAlbums = byArtist.get(artistId);
      if (artistAlbums) artistAlbums.push(album);
      else byArtist.set(artistId, [album]);
    }
    return byArtist;
  }, [albums]);

  // Filter content based on active tab and search query. Name matches are
  // done locally; an item whose name doesn't match still shows up when one of
  // its tracks does, with a hint saying which one.
  const query = searchQuery.toLowerCase();

  const filteredArtists = useMemo(
    () => activeTab === 'albums' ? [] : artists.filter(artist =>
      artist.name?.toLowerCase().includes(query) || artistTrackMatches.has(artist.id)
    ),
    [artists, activeTab, query, artistTrackMatches]
  );

  const filteredAlbums = useMemo(
    () => activeTab === 'artists' ? [] : albums.filter(album =>
      album.title?.toLowerCase().includes(query) ||
      (album.artist_name || album.artist?.name)?.toLowerCase().includes(query) ||
      albumTrackMatches.has(album.id)
    ),
    [albums, activeTab, query, albumTrackMatches]
  );

  // Large libraries hold thousands of albums: mount the cards a page at a
  // time as the user scrolls, starting over on a new search or tab
  const listResetKey = `${activeTab}|${query}`;
  const {
    visible: displayedArtists,
    hasMore: moreArtists,
    sentinelRef: artistsSentinelRef,
  } = useProgressiveList(filteredArtists, PAGE_SIZE, listResetKey);
  const {
    visible: displayedAlbums,
    hasMore: moreAlbums,
    sentinelRef: albumsSentinelRef,
  } = useProgressiveList(filteredAlbums, PAGE_SIZE, listResetKey);

  const albumMatchHint = (albumId: string): string | undefined => {
    const matches = albumTrackMatches.get(albumId);
    if (!matches?.length) return undefined;
    return matches.length === 1
      ? t('library.trackMatch.one', { title: matches[0].title })
      : t('library.trackMatch.many', { title: matches[0].title, count: matches.length - 1 });
  };

  const artistMatchHint = (artistId: string): string | undefined => {
    const matches = artistTrackMatches.get(artistId);
    if (!matches?.length) return undefined;
    const first = matches[0];
    const albumTitle = first.album?.title || albumTitleById.get(first.album?.id || '') || '';
    return matches.length === 1
      ? t('library.trackMatch.artistOne', { title: first.title, album: albumTitle })
      : t('library.trackMatch.artistMany', { title: first.title, count: matches.length - 1 });
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

  // Followed artists/albums/charts as a JSON file: shareable, and importable
  // by an admin on another instance (Admin panel > Backup).
  const handleExport = async () => {
    setExporting(true);
    try {
      downloadJson(await exportLibrary(), exportFilename('library'));
    } catch (err: any) {
      console.error('Failed to export library:', err);
      setError(parseApiError(err, 'Failed to export library'));
    } finally {
      setExporting(false);
    }
  };

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
              <span className="text-foreground">{t('library.heroYour')} </span>
              <span className="text-gradient">{t('library.heroLibrary')}</span>
            </>
          }
          subtitle={t('library.heroSubtitle')}
          actions={hasContent && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              isLoading={exporting}
              className="gap-2 glass"
              title={t('library.export.description')}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v12m0 0l-4-4m4 4l4-4M4 17v2a1 1 0 001 1h14a1 1 0 001-1v-2" />
              </svg>
              {t('library.export.button')}
            </Button>
          )}
        />

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              icon={<ArtistsIcon />}
              label={t('library.stats.artists')}
              value={formatNumber(stats.artists?.total || 0)}
            />
            <StatCard
              icon={<AlbumsIcon />}
              label={t('library.stats.albums')}
              value={formatNumber(stats.albums?.completed || 0)}
            />
            <StatCard
              icon={<TracksIcon />}
              label={t('library.stats.tracks')}
              value={formatNumber(stats.tracks?.downloaded || 0)}
            />
            <StatCard
              icon={<ActivityIcon />}
              label={t('library.stats.diskUsage')}
              value={loading ? <Spinner size="sm" /> : `${stats?.storage?.gb?.toFixed(1) || 0} GB`}
              loading={loading}
              info={t('library.stats.diskUsageInfo')}
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
                {t('library.emptyTitle')}
              </h3>
              <p className="text-muted-foreground mb-8">
                {t('library.emptyDescription')}
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
            {/* Filter tabs and search */}
            <div className="flex flex-col md:flex-row items-start md:items-center gap-4 justify-between">
              {/* Filter tabs */}
              <div className="flex items-center gap-2 glass rounded-2xl p-2">
                <button
                  onClick={() => setActiveTab('all')}
                  className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                    activeTab === 'all'
                      ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                      : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                  }`}
                >
                  {t('common.all')}
                </button>
                <button
                  onClick={() => setActiveTab('artists')}
                  className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                    activeTab === 'artists'
                      ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                      : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                  }`}
                >
                  {t('browse.sections.artists')} ({artists.length})
                </button>
                <button
                  onClick={() => setActiveTab('albums')}
                  className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                    activeTab === 'albums'
                      ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                      : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                  }`}
                >
                  {t('browse.sections.albums')} ({albums.length})
                </button>
              </div>

              {/* Search bar + view switch - the input stretches to the toggle's height */}
              <div className="flex items-stretch gap-3 w-full md:w-auto">
                <SearchInput
                  value={searchQuery}
                  onChange={setSearchQuery}
                  placeholder={t('library.searchPlaceholder')}
                  size="md"
                  showClearButton
                  onClear={() => setSearchQuery('')}
                  className="flex-1 md:flex-none md:w-64 lg:w-96"
                  inputClassName="h-full"
                />
                <ViewToggle value={viewMode} onChange={setViewMode} />
              </div>
            </div>

            {/* Followed Artists */}
            {displayedArtists.length > 0 && (
              <section>
                <SectionHeader>
                  {t('library.artists')}
                </SectionHeader>
                {viewMode === 'grid' ? (
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                    {displayedArtists.map((artist) => (
                      <MediaCard
                        key={artist.id}
                        id={artist.id}
                        title={artist.name}
                        thumbnail={getImageUrl(artist.image_local || artist.thumbnail)}
                        type="artist"
                        mediaStatus={getArtistStatus(artist, albumsByArtist.get(artist.id))}
                        matchHint={artistMatchHint(artist.id)}
                        onClick={() => navigate(`/artists/${encodeURIComponent(artist.id)}`)}
                      />
                    ))}
                  </div>
                ) : (
                  <MediaList kind="artist">
                    {displayedArtists.map((artist) => (
                      <MediaRow
                        key={artist.id}
                        id={artist.id}
                        title={artist.name}
                        thumbnail={getImageUrl(artist.image_local || artist.thumbnail)}
                        type="artist"
                        mediaStatus={getArtistStatus(artist, albumsByArtist.get(artist.id))}
                        albumsCount={artist.albums_count}
                        tracksTotal={artist.tracks_total}
                        tracksDownloaded={artist.tracks_downloaded}
                        date={artist.followed_at}
                        matchHint={artistMatchHint(artist.id)}
                        onClick={() => navigate(`/artists/${encodeURIComponent(artist.id)}`)}
                      />
                    ))}
                  </MediaList>
                )}
                {moreArtists && <div ref={artistsSentinelRef} aria-hidden="true" />}
              </section>
            )}

            {/* Followed Albums */}
            {displayedAlbums.length > 0 && (
              <section>
                <SectionHeader>
                  {t('library.albums')}
                </SectionHeader>
                {viewMode === 'grid' ? (
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                    {displayedAlbums.map((album) => (
                      <MediaCard
                        key={album.id}
                        id={album.id}
                        title={album.title}
                        subtitle={album.artist_name || album.artist?.name}
                        thumbnail={getImageUrl(album.image_local || album.thumbnail)}
                        type="album"
                        albumType={album.type}
                        year={album.year}
                        mediaStatus={getAlbumStatus(album)}
                        matchHint={albumMatchHint(album.id)}
                        onClick={() => navigate(`/albums/${encodeURIComponent(album.id)}`)}
                      />
                    ))}
                  </div>
                ) : (
                  <MediaList kind="album">
                    {displayedAlbums.map((album) => (
                      <MediaRow
                        key={album.id}
                        id={album.id}
                        title={album.title}
                        subtitle={album.artist_name || album.artist?.name}
                        thumbnail={getImageUrl(album.image_local || album.thumbnail)}
                        type="album"
                        albumType={album.type}
                        year={album.year}
                        mediaStatus={getAlbumStatus(album)}
                        tracksTotal={album.tracks_total}
                        tracksDownloaded={album.tracks_downloaded}
                        date={album.created_at}
                        matchHint={albumMatchHint(album.id)}
                        onClick={() => navigate(`/albums/${encodeURIComponent(album.id)}`)}
                      />
                    ))}
                  </MediaList>
                )}
                {moreAlbums && <div ref={albumsSentinelRef} aria-hidden="true" />}
              </section>
            )}

            {/* No results from search - wait for the track lookup so it doesn't flash */}
            {searchQuery && trackMatchesReady && displayedArtists.length === 0 && displayedAlbums.length === 0 && (
              <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-12 border border-slate-200/50 dark:border-white/10 text-center">
                <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-4">
                  <span className="text-4xl">🔍</span>
                </div>
                <h3 className="text-xl font-semibold text-foreground mb-2">{t('library.noMatches')}</h3>
                <p className="text-muted-foreground">
                  {t('library.noMatchesDescription')} <span className="font-semibold text-foreground">"{searchQuery}"</span>
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}