// src/pages/Library.tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { useAuth } from '../contexts/AuthContext';
import { useFeatures } from '../contexts/FeaturesContext';
import { useJobActivity } from '../contexts/JobActivityContext';
import { getLibraryArtists, getLibraryAlbums, getLibraryStats, searchLibraryTracks } from '../api/library';
import type { LibraryAlbum, LibraryArtist, LibraryStats, LibraryTrack } from '../api/library';
import { exportLibrary, downloadJson, exportFilename } from '../api/export';
import { listPlaylists } from '../api/playlists';
import type { SavedPlaylist } from '../api/playlists';
import { getImageUrl } from '../api/media';
import { PlaylistsPanel } from '../components/playlists/PlaylistsPanel';
import { LibraryStatCards } from '../components/LibraryStatCards';
import { MEDIA_GRID, MediaCard } from '../components/MediaCard';
import { MediaList, MediaRow } from '../components/MediaList';
import { Button } from '../components/ui/Button';
import { LikeButton } from '../components/ui/LikeButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHeader } from '../components/ui/PageHeader';
import { SearchInput } from '../components/ui/SearchInput';
import { FilterTabs } from '../components/ui/FilterTabs';
import { Toast } from '../components/ui/Toast';
import { EmptyState, ErrorBanner, LoadingState } from '../components/ui/PageStatus';
import { ViewToggle, type ViewMode } from '../components/ui/ViewToggle';
import { apiErrorMessage, getAlbumStatus, getArtistStatus, createMemoryCache, artistPath, albumPath, exceptionalStatus } from '../utils';
import { useDebounce } from '../hooks/useDebounce';
import { useProgressiveList } from '../hooks/useProgressiveList';
import { useHistoryState } from '../hooks/useHistoryState';
import { useLikeSync } from '../hooks/useLikeSync';
import { Icon } from '../components/ui/icons';
import { ActiveFilters, LibraryFilterControl, SortControl, filterHintText } from '../components/library/LibraryFilters';
import {
  FILTER_GROUPS,
  activeFilterCount,
  albumHints,
  albumMatches,
  artistHints,
  artistMatches,
  filtersFromParams,
  sortAlbums,
  sortArtists,
  sortFromParams,
  toggleFilter,
  withFilterParams,
} from '../utils/libraryFilters';
import type { FilterContext, FilterGroup, FilterHint, FilterItems, LibraryFilters, LibrarySort, OfferedFilters } from '../utils/libraryFilters';

type LibraryTab = 'all' | 'artists' | 'albums' | 'playlists';

const VIEW_STORAGE_KEY = 'library.view';
const TRACK_SEARCH_DEBOUNCE_MS = 250;
/** Shortest gap between two refreshes triggered by the job queue */
const REFRESH_MIN_GAP_MS = 5000;
/** Cards mounted per scroll step: a multiple of every grid column count (2 to 5) */
const PAGE_SIZE = 60;

/** Tracks matching the search, grouped by the album / artist they belong to */
interface TrackMatches {
  /** The query these results answer: lets the UI tell fresh results from stale ones */
  query: string;
  byAlbum: Map<string, LibraryTrack[]>;
  byArtist: Map<string, LibraryTrack[]>;
}

const NO_TRACK_MATCHES: TrackMatches = { query: '', byAlbum: new Map(), byArtist: new Map() };

/** What the page last loaded: shown right away when coming back, then refreshed */
interface LibrarySnapshot {
  artists: LibraryArtist[];
  albums: LibraryAlbum[];
  stats: LibraryStats;
  playlists: SavedPlaylist[];
}

const LIBRARY_CACHE_KEY = 'library';
const libraryCache = createMemoryCache<LibrarySnapshot>(1);
/** Track search results by query */
const trackMatchesCache = createMemoryCache<TrackMatches>(20);

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

/** One line under a card or row: why it's listed, from the search and from the filters */
function joinHints(...parts: Array<string | undefined>): string | undefined {
  return parts.filter(Boolean).join(' · ') || undefined;
}

function loadViewMode(): ViewMode {
  try {
    return localStorage.getItem(VIEW_STORAGE_KEY) === 'list' ? 'list' : 'grid';
  } catch {
    return 'grid';
  }
}

export default function Library(): JSX.Element {
  const [cached] = useState(() => libraryCache.get(LIBRARY_CACHE_KEY));
  const [artists, setArtists] = useState<LibraryArtist[]>(cached?.artists ?? []);
  const [albums, setAlbums] = useState<LibraryAlbum[]>(cached?.albums ?? []);
  const [stats, setStats] = useState<LibraryStats | null>(cached?.stats ?? null);
  const [loading, setLoading] = useState(!cached);
  // The first load's failure (a failed background refresh keeps what's on screen)
  const [loadError, setLoadError] = useState<unknown>(null);
  const [toast, setToast] = useState<string | null>(null);
  // Bumped by every library refresh: the track search follows it
  const [libraryVersion, setLibraryVersion] = useState(0);
  // Tab and search come back with the back button, along with the scroll position
  const [activeTab, setActiveTab] = useHistoryState<LibraryTab>('tab', 'all');
  const [playlists, setPlaylists] = useState<SavedPlaylist[]>(cached?.playlists ?? []);
  const [searchQuery, setSearchQuery] = useHistoryState('search', '');
  const [trackMatches, setTrackMatches] = useState<TrackMatches>(
    () => trackMatchesCache.get(searchQuery.trim()) ?? NO_TRACK_MATCHES
  );
  const [viewMode, setViewMode] = useState<ViewMode>(loadViewMode);
  const [exporting, setExporting] = useState(false);
  const debouncedQuery = useDebounce(searchQuery.trim(), TRACK_SEARCH_DEBOUNCE_MS);
  const navigate = useNavigate();
  const { t, formatLocale } = useI18n();
  const { user } = useAuth();
  const { features } = useFeatures();
  // Filters and sort are in the URL: a link can open the library filtered,
  // and the back button brings them back
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => filtersFromParams(searchParams), [searchParams]);
  const sort = useMemo(() => sortFromParams(searchParams), [searchParams]);
  const filtersActive = activeFilterCount(filters) > 0;
  // The filter popover stays within the toolbar's width
  const toolbarRef = useRef<HTMLDivElement>(null);
  // Visitors are read-only: liking is a member+ action on the backend
  const canLike = user?.role === 'administrator' || user?.role === 'member';
  const { revision } = useJobActivity();
  // On screen and in the cache, for coming back
  const setLiked = (artistId: string, liked: boolean) => {
    setArtists((current) => current.map((a) => (a.id === artistId ? { ...a, liked } : a)));
    const snapshot = libraryCache.get(LIBRARY_CACHE_KEY);
    if (snapshot) {
      libraryCache.set(LIBRARY_CACHE_KEY, {
        ...snapshot,
        artists: snapshot.artists.map((a) => (a.id === artistId ? { ...a, liked } : a)),
      });
    }
  };
  // Put back if the server says no
  const likeSync = useLikeSync((artistId, liked) => {
    setLiked(artistId, liked);
    setToast(t('artist.likeError'));
  });
  const { unsaved: unsavedLikes } = likeSync;

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, viewMode);
    } catch {
      // Storage unavailable - the choice just won't survive a reload
    }
  }, [viewMode]);

  // Kept in a ref so the effects below don't refire on it
  const fetchRef = useRef({ loaded: !!cached, inFlight: false, queued: false, lastStartedAt: 0, unmounted: false });

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
      const [artistsList, albumsList, statsResponse, playlistsResponse] = await Promise.all([
        getLibraryArtists(),
        getLibraryAlbums(),
        getLibraryStats(),
        // The rest of the page doesn't depend on it
        listPlaylists().catch((err) => {
          console.error('Failed to load playlists:', err);
          return null;
        }),
      ]);

      // Hearts clicked but not saved yet keep what the screen shows
      const likes = unsavedLikes();
      const snapshot: LibrarySnapshot = {
        artists: artistsList.map((a) => (likes.has(a.id) ? { ...a, liked: likes.get(a.id)! } : a)),
        albums: albumsList,
        stats: statsResponse,
        // A failed playlists fetch keeps the ones already shown (the
        // callback never changes, so state would be stale here)
        playlists: playlistsResponse ?? libraryCache.get(LIBRARY_CACHE_KEY)?.playlists ?? [],
      };
      libraryCache.set(LIBRARY_CACHE_KEY, snapshot);

      if (state.unmounted) return;
      setArtists(snapshot.artists);
      setAlbums(snapshot.albums);
      setStats(snapshot.stats);
      if (playlistsResponse) setPlaylists(playlistsResponse);
      setLibraryVersion((version) => version + 1);
      setLoadError(null);
      state.loaded = true;
    } catch (err: any) {
      console.error('Failed to load library:', err);
      if (!state.unmounted && !state.loaded) setLoadError(err);
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
  // badges follow downloads started from anywhere, including ones this page
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
  // server and the matching albums / artists are surfaced instead. Searched
  // again when the library is refreshed, with the tracks it now holds.
  useEffect(() => {
    if (!debouncedQuery) {
      setTrackMatches(NO_TRACK_MATCHES);
      return;
    }

    let cancelled = false;

    searchLibraryTracks(debouncedQuery)
      .then((tracks) => {
        const matches = groupTrackMatches(debouncedQuery, tracks);
        trackMatchesCache.set(debouncedQuery, matches);
        if (!cancelled) setTrackMatches(matches);
      })
      .catch((err) => {
        console.error('Failed to search library tracks:', err);
        if (!cancelled) setTrackMatches({ ...NO_TRACK_MATCHES, query: debouncedQuery });
      });

    return () => { cancelled = true; };
  }, [debouncedQuery, libraryVersion]);

  // Results are only shown once they answer the current input, so a query the
  // user has moved on from never leaks stale hints. A refetch triggered by a
  // library refresh keeps the previous results on screen until the new ones land,
  // instead of blanking them on every tick.
  const trackMatchesReady = trackMatches.query === searchQuery.trim();
  const albumTrackMatches = trackMatchesReady ? trackMatches.byAlbum : NO_TRACK_MATCHES.byAlbum;
  const artistTrackMatches = trackMatchesReady ? trackMatches.byArtist : NO_TRACK_MATCHES.byArtist;

  const albumTitleById = useMemo(
    () => new Map<string, string>(albums.map((album) => [album.id, album.title])),
    [albums]
  );

  // An artist's badge depends on its albums: grouped once instead of
  // scanning every album for every artist card
  const albumsByArtist = useMemo(() => {
    const byArtist = new Map<string, LibraryAlbum[]>();
    for (const album of albums) {
      const artistId = album.artist?.id;
      if (!artistId) continue;
      const artistAlbums = byArtist.get(artistId);
      if (artistAlbums) artistAlbums.push(album);
      else byArtist.set(artistId, [album]);
    }
    return byArtist;
  }, [albums]);

  // The status of each item, worked out once. Cards badge only the exceptions;
  // a list shows its status column when some row is one, and then fills every row
  const artistStatus = useMemo(
    () => new Map(artists.map((artist) => [artist.id, getArtistStatus(artist, albumsByArtist.get(artist.id))])),
    [artists, albumsByArtist]
  );
  const albumStatus = useMemo(
    () => new Map(albums.map((album) => [album.id, getAlbumStatus(album)])),
    [albums]
  );

  // Filter content based on active tab and search query. Name matches are
  // done locally; an item whose name doesn't match still shows up when one of
  // its tracks does, with a hint saying which one.
  const query = searchQuery.toLowerCase();

  const searchedArtists = useMemo(
    () => activeTab === 'albums' || activeTab === 'playlists' ? [] : artists.filter(artist =>
      artist.name.toLowerCase().includes(query) || artistTrackMatches.has(artist.id)
    ),
    [artists, activeTab, query, artistTrackMatches]
  );

  const searchedAlbums = useMemo(
    () => activeTab === 'artists' || activeTab === 'playlists' ? [] : albums.filter(album =>
      album.title.toLowerCase().includes(query) ||
      album.artist?.name.toLowerCase().includes(query) ||
      albumTrackMatches.has(album.id)
    ),
    [albums, activeTab, query, albumTrackMatches]
  );

  // Then the filters (see utils/libraryFilters.ts) and the sort
  const artistById = useMemo(() => new Map(artists.map((artist) => [artist.id, artist])), [artists]);
  const filterContext = useMemo<FilterContext>(
    () => ({ artistById, albumsByArtist, albumStatus }),
    [artistById, albumsByArtist, albumStatus]
  );
  const collator = useMemo(() => new Intl.Collator(formatLocale, { sensitivity: 'base', numeric: true }), [formatLocale]);

  const filteredArtists = useMemo(() => {
    const matching = filtersActive ? searchedArtists.filter((artist) => artistMatches(artist, filters, filterContext)) : searchedArtists;
    return sortArtists(matching, sort, filterContext, collator);
  }, [searchedArtists, filters, filtersActive, sort, filterContext, collator]);

  const filteredAlbums = useMemo(() => {
    const matching = filtersActive ? searchedAlbums.filter((album) => albumMatches(album, filters, filterContext)) : searchedAlbums;
    return sortAlbums(matching, sort, collator);
  }, [searchedAlbums, filters, filtersActive, sort, filterContext, collator]);

  // Lyrics filters only when lyrics are fetched; "No genre found" only when genres are looked up
  const lyricsEnabled = !!features?.lyrics_enabled;
  const genresEnabled = !!features?.genres_enabled;
  const offeredFilters = useMemo<OfferedFilters>(() => ({
    groups: FILTER_GROUPS.filter((group) => group !== 'lyrics' || lyricsEnabled),
    genresLookedUp: genresEnabled,
  }), [lyricsEnabled, genresEnabled]);
  // For the filter panel's counts
  const libraryItems = useMemo<FilterItems>(() => ({ artists, albums }), [artists, albums]);
  const shownItems = useMemo<FilterItems>(
    () => ({ artists: searchedArtists, albums: searchedAlbums }),
    [searchedArtists, searchedAlbums]
  );

  // Written to the URL in place: picking filters adds no history entries
  const updateFilters = useCallback(
    (change: (current: LibraryFilters, sort: LibrarySort) => [LibraryFilters, LibrarySort]) => {
      setSearchParams((prev) => {
        const [nextFilters, nextSort] = change(filtersFromParams(prev), sortFromParams(prev));
        return withFilterParams(prev, nextFilters, nextSort);
      }, { replace: true });
    },
    [setSearchParams]
  );
  const onToggleFilter = (group: FilterGroup, value: string) =>
    updateFilters((current, currentSort) => [toggleFilter(current, group, value), currentSort]);
  const clearFilters = () => updateFilters((_current, currentSort) => [{}, currentSort]);
  const setSort = (next: LibrarySort) => updateFilters((current) => [current, next]);

  const filterHint = (found: FilterHint[]): string | undefined =>
    found.length > 0 ? found.map((hint) => filterHintText(t, hint)).join(' · ') : undefined;

  // Large libraries hold thousands of albums: mount the cards a page at a
  // time as the user scrolls, starting over on a new search, tab, filter or sort
  const listResetKey = `${activeTab}|${query}|${withFilterParams(new URLSearchParams(), filters, sort).toString()}`;
  const {
    visible: displayedArtists,
    hasMore: moreArtists,
    sentinelRef: artistsSentinelRef,
  } = useProgressiveList(filteredArtists, PAGE_SIZE, listResetKey, 'artists');
  const {
    visible: displayedAlbums,
    hasMore: moreAlbums,
    sentinelRef: albumsSentinelRef,
  } = useProgressiveList(filteredAlbums, PAGE_SIZE, listResetKey, 'albums');

  const albumHint = (album: LibraryAlbum): string | undefined =>
    joinHints(albumMatchHint(album.id), filtersActive ? filterHint(albumHints(album, filters)) : undefined);
  const artistHint = (artist: LibraryArtist): string | undefined =>
    joinHints(artistMatchHint(artist.id), filtersActive ? filterHint(artistHints(artist, filters, filterContext)) : undefined);

  const albumMatchHint = (albumId: string): string | undefined => {
    const matches = albumTrackMatches.get(albumId);
    if (!matches?.length) return undefined;
    return matches.length === 1
      ? t('library.trackMatch.one', { title: matches[0].title })
      : t('library.trackMatch.many', { title: matches[0].title, count: matches.length - 1 });
  };

  // An album's artist name links to the artist, when we know who it is
  const albumArtistPath = (album: LibraryAlbum): string | undefined =>
    album.artist?.id ? artistPath(album.artist.id) : undefined;

  const artistMatchHint = (artistId: string): string | undefined => {
    const matches = artistTrackMatches.get(artistId);
    if (!matches?.length) return undefined;
    const first = matches[0];
    const albumTitle = first.album.title || albumTitleById.get(first.album.id) || '';
    return matches.length === 1
      ? t('library.trackMatch.artistOne', { title: first.title, album: albumTitle })
      : t('library.trackMatch.artistMany', { title: first.title, count: matches.length - 1 });
  };

  if (loading) return <LoadingState />;
  if (loadError) return <ErrorBanner title={t('common.error')}>{apiErrorMessage(loadError, t, t('common.error'))}</ErrorBanner>;

  const hasContent = artists.length > 0 || albums.length > 0;

  // Followed artists/albums/charts as a JSON file: shareable, and importable
  // by an admin on another instance (Admin panel > Backup).
  const handleExport = async () => {
    setExporting(true);
    try {
      downloadJson(await exportLibrary(), exportFilename('library'));
    } catch (err: any) {
      console.error('Failed to export library:', err);
      setToast(apiErrorMessage(err, t, t('library.export.failed')));
    } finally {
      setExporting(false);
    }
  };

  const tabs = [
    { id: 'all' as const, label: t('common.all') },
    { id: 'artists' as const, label: `${t('browse.sections.artists')} (${artists.length})` },
    { id: 'albums' as const, label: `${t('browse.sections.albums')} (${albums.length})` },
    ...(playlists.length > 0 || activeTab === 'playlists'
      ? [{ id: 'playlists' as const, label: `${t('library.playlists')} (${playlists.length})` }]
      : []),
  ];

  // Flipped right away; the server hears of it once the clicks stop (useLikeSync)
  const toggleLike = (artist: LibraryArtist) => {
    const liked = !artist.liked;
    setLiked(artist.id, liked);
    likeSync.toggle(artist.id, liked);
  };

  return (
    <div className="space-y-8 pb-12">
      {toast && <Toast message={toast} type="error" onClose={() => setToast(null)} />}

      <PageHeader
        icon="library"
        title={t('nav.library')}
        subtitle={t('library.heroSubtitle')}
        actions={hasContent && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            isLoading={exporting}
            className="gap-2"
            title={t('library.export.description')}
          >
            <Icon name="download" className="w-4 h-4" />
            {t('library.export.button')}
          </Button>
        )}
      />

      <LibraryStatCards stats={stats} />

      {!hasContent ? (
        <EmptyState icon="library" title={t('library.emptyTitle')}>
          <p>{t('library.emptyDescription')}</p>
          <Button variant="primary" size="lg" onClick={() => navigate('/browse')} className="gap-2">
            <Icon name="search" />
            {t('nav.browse')}
          </Button>
        </EmptyState>
      ) : (
        <>
          {/* Search, filters and sort on the left, tabs and view switch on the right.
              Below xl they take a row each: search, filters and sort on top,
              tabs and view switch under them; the tabs scroll sideways when
              they don't fit beside the switch. Phones keep the sort in the
              filter sheet. Everything stretches to the row's height.
              The picked filters line up under it all. */}
          <div ref={toolbarRef} className="space-y-3">
            <div className="flex flex-wrap xl:flex-nowrap items-stretch gap-3 xl:gap-4">
              <div className="flex items-stretch gap-2 md:gap-3 basis-full xl:basis-auto min-w-0">
                <SearchInput
                  value={searchQuery}
                  onChange={setSearchQuery}
                  placeholder={t('library.searchPlaceholder')}
                  size="md"
                  className="flex-1 min-w-0 xl:flex-none xl:w-72 2xl:w-96"
                  inputClassName="h-full"
                />
                {activeTab !== 'playlists' && (
                  <>
                    <LibraryFilterControl
                      filters={filters}
                      onToggle={onToggleFilter}
                      onClear={clearFilters}
                      shown={shownItems}
                      library={libraryItems}
                      context={filterContext}
                      offered={offeredFilters}
                      collator={collator}
                      resultCount={filteredArtists.length + filteredAlbums.length}
                      sort={sort}
                      onSortChange={setSort}
                      boundsRef={toolbarRef}
                    />
                    <SortControl sort={sort} onChange={setSort} className="hidden md:flex w-56" />
                  </>
                )}
              </div>
              <div className="flex-1 xl:flex-none xl:ml-auto min-w-0">
                <FilterTabs
                  tabs={tabs}
                  active={activeTab}
                  onChange={setActiveTab}
                  className="overflow-x-auto no-scrollbar"
                />
              </div>
              {activeTab !== 'playlists' && <ViewToggle value={viewMode} onChange={setViewMode} />}
            </div>

            {activeTab !== 'playlists' && (
              <ActiveFilters
                filters={filters}
                onToggle={onToggleFilter}
                onClear={clearFilters}
                resultCount={filteredArtists.length + filteredAlbums.length}
              />
            )}
          </div>

          {activeTab === 'playlists' && (
            <PlaylistsPanel
              playlists={playlists.filter((p) => p.title.toLowerCase().includes(query))}
              onChanged={loadLibrary}
            />
          )}

          {displayedArtists.length > 0 && (
            <section>
              <SectionHeader>{t('library.artists')}</SectionHeader>
              {viewMode === 'grid' ? (
                <div className={MEDIA_GRID}>
                  {displayedArtists.map((artist) => (
                    <MediaCard
                      key={artist.id}
                      id={artist.id}
                      title={artist.name}
                      subtitle={t('library.meta.albumCount', { count: artist.albums_count })}
                      thumbnail={getImageUrl(artist.thumbnail)}
                      type="artist"
                      mediaStatus={exceptionalStatus(artistStatus.get(artist.id))}
                      matchHint={artistHint(artist)}
                      to={artistPath(artist.id)}
                      titleAction={canLike && (
                        // Next to the name, as in the list view; a liked artist always shows its heart, the others on hover
                        <LikeButton
                          liked={artist.liked}
                          name={artist.name}
                          onToggle={() => toggleLike(artist)}
                          className={`w-7 h-7 text-muted-foreground hover:text-foreground hover:bg-slate-200/70 dark:hover:bg-white/10 transition-all ${
                            artist.liked ? '' : '[@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100'
                          }`}
                        />
                      )}
                    />
                  ))}
                </div>
              ) : (
                <MediaList
                  kind="artist"
                  showStatus={displayedArtists.some((artist) => exceptionalStatus(artistStatus.get(artist.id)))}
                >
                  {displayedArtists.map((artist) => (
                    <MediaRow
                      key={artist.id}
                      id={artist.id}
                      title={artist.name}
                      thumbnail={getImageUrl(artist.thumbnail)}
                      type="artist"
                      mediaStatus={artistStatus.get(artist.id)}
                      albumsCount={artist.albums_count}
                      tracksTotal={artist.tracks_total}
                      tracksDownloaded={artist.tracks_downloaded}
                      date={artist.followed_at}
                      matchHint={artistHint(artist)}
                      to={artistPath(artist.id)}
                      titleAction={canLike && (
                        // A liked artist always shows its heart, the others on hover
                        <LikeButton
                          liked={artist.liked}
                          name={artist.name}
                          onToggle={() => toggleLike(artist)}
                          className={`w-7 h-7 text-muted-foreground hover:text-foreground hover:bg-slate-200/70 dark:hover:bg-white/10 transition-all ${
                            artist.liked ? '' : '[@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100'
                          }`}
                        />
                      )}
                    />
                  ))}
                </MediaList>
              )}
              {moreArtists && <div ref={artistsSentinelRef} aria-hidden="true" />}
            </section>
          )}

          {displayedAlbums.length > 0 && (
            <section>
              <SectionHeader>{t('library.albums')}</SectionHeader>
              {viewMode === 'grid' ? (
                <div className={MEDIA_GRID}>
                  {displayedAlbums.map((album) => (
                    <MediaCard
                      key={album.id}
                      id={album.id}
                      title={album.title}
                      subtitle={album.artist?.name}
                      subtitleTo={albumArtistPath(album)}
                      thumbnail={getImageUrl(album.thumbnail)}
                      type="album"
                      albumType={album.type}
                      year={album.year ?? undefined}
                      mediaStatus={exceptionalStatus(albumStatus.get(album.id))}
                      matchHint={albumHint(album)}
                      to={albumPath(album.id)}
                    />
                  ))}
                </div>
              ) : (
                <MediaList kind="album" showStatus={displayedAlbums.some((album) => exceptionalStatus(albumStatus.get(album.id)))}>
                  {displayedAlbums.map((album) => (
                    <MediaRow
                      key={album.id}
                      id={album.id}
                      title={album.title}
                      subtitle={album.artist?.name}
                      subtitleTo={albumArtistPath(album)}
                      thumbnail={getImageUrl(album.thumbnail)}
                      type="album"
                      albumType={album.type}
                      year={album.year ?? undefined}
                      mediaStatus={albumStatus.get(album.id)}
                      tracksTotal={album.tracks_total}
                      tracksDownloaded={album.tracks_downloaded}
                      date={album.created_at}
                      matchHint={albumHint(album)}
                      to={albumPath(album.id)}
                    />
                  ))}
                </MediaList>
              )}
              {moreAlbums && <div ref={albumsSentinelRef} aria-hidden="true" />}
            </section>
          )}

          {/* No results from search or filters; waits for the track lookup so it doesn't flash */}
          {(searchQuery || filtersActive) && activeTab !== 'playlists' && trackMatchesReady && displayedArtists.length === 0 && displayedAlbums.length === 0 && (
            filtersActive ? (
              <EmptyState icon="filter" title={t('library.filters.noMatchesTitle')}>
                <p>
                  {searchQuery
                    ? t('library.filters.noMatchesWithSearch', { query: searchQuery })
                    : t('library.filters.noMatchesDescription')}
                </p>
                <Button variant="primary" onClick={clearFilters}>{t('library.filters.clear')}</Button>
              </EmptyState>
            ) : (
              <EmptyState icon="search" title={t('library.noMatches')}>
                <p>{t('library.noMatchesDescription', { query: searchQuery })}</p>
              </EmptyState>
            )
          )}
        </>
      )}
    </div>
  );
}
