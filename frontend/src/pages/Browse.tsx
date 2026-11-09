// src/pages/Browse.tsx
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { useAuth } from '../contexts/AuthContext';
import { search } from '../api/search';
import type { SearchResults, SearchSong } from '../api/search';
import { getImageUrl } from '../api/media';
import { CardLink, MEDIA_GRID, MediaCard, SubtitleLink } from '../components/MediaCard';
import { Artwork } from '../components/ui/Artwork';
import { RecommendedArtists } from '../components/RecommendedArtists';
import { QuickFollowButton } from '../components/QuickFollowButton';
import { SearchInput } from '../components/ui/SearchInput';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHeader } from '../components/ui/PageHeader';
import { FilterTabs } from '../components/ui/FilterTabs';
import type { FilterTab } from '../components/ui/FilterTabs';
import { EmptyState, ErrorBanner } from '../components/ui/PageStatus';
import { apiErrorMessage, createMemoryCache, artistPath, albumPath } from '../utils';
import { useDebounce } from '../hooks/useDebounce';
import { Icon } from '../components/ui/icons';

const VALID_FILTERS = ['all', 'artists', 'albums', 'songs'] as const;
type FilterType = typeof VALID_FILTERS[number];

const EMPTY_RESULTS: SearchResults = { artists: [], albums: [], songs: [] };

/** Results by query: coming back to a search shows them right away */
const resultsCache = createMemoryCache<SearchResults>(20);

/** One song result: a row, since a song is a line in a list, not a cover. Opens its album */
function SongRow({ song }: { song: SearchSong }): JSX.Element {
  const artist = song.artists[0]?.name;
  const artistId = song.artists[0]?.id;
  return (
    <div className="group relative flex items-center gap-3 px-3 md:px-4 py-2.5 transition-colors hover:bg-slate-100/70 dark:hover:bg-white/5">
      {song.album.id && <CardLink to={albumPath(song.album.id)} label={song.title} className="w-full focus-visible:ring-inset" />}
      <div className="contents pointer-events-none">
        <Artwork
          src={getImageUrl(song.thumbnail)}
          kind="track"
          className="w-11 h-11 shrink-0 rounded-lg overflow-hidden ring-1 ring-slate-900/5 dark:ring-white/10"
        />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-sm text-foreground truncate group-hover:text-accent-600 dark:group-hover:text-accent-400 transition-colors">{song.title}</p>
          <p className="text-xs text-muted-foreground truncate">
            {artist && (artistId ? <SubtitleLink to={artistPath(artistId)}>{artist}</SubtitleLink> : artist)}
            {artist && song.album.name && ' · '}
            {song.album.name}
          </p>
        </div>
      </div>
    </div>
  );
}

export default function Browse(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const filterParam = searchParams.get('filter');
  const activeFilter: FilterType = VALID_FILTERS.includes(filterParam as FilterType)
    ? (filterParam as FilterType)
    : 'all';

  // Local state for responsive typing; URL params sync only after debounce
  const [query, setQuery] = useState(searchParams.get('q') || '');

  const setActiveFilter = useCallback((newFilter: FilterType) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (newFilter !== 'all') {
        next.set('filter', newFilter);
      } else {
        next.delete('filter');
      }
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const [results, setResults] = useState<SearchResults>(
    () => resultsCache.get(query.trim()) ?? EMPTY_RESULTS
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useI18n();
  const { user } = useAuth();
  // Visitors are read-only: following is a member+ action on the backend
  const canFollow = user?.role === 'administrator' || user?.role === 'member';

  const debouncedQuery = useDebounce(query, 500);

  // Sync debounced query to URL params (single history replace, not per-keystroke)
  useEffect(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (debouncedQuery) {
        next.set('q', debouncedQuery);
      } else {
        next.delete('q');
      }
      return next;
    }, { replace: true });
  }, [debouncedQuery, setSearchParams]);

  // Search when the debounced query changes
  useEffect(() => {
    const trimmed = debouncedQuery.trim();
    setError(null);

    if (!trimmed) {
      setResults(EMPTY_RESULTS);
      setLoading(false);
      return;
    }

    // Shown right away, then refreshed quietly: who's followed may have changed since
    const cached = resultsCache.get(trimmed);
    if (cached) setResults(cached);

    let cancelled = false;
    setLoading(!cached);

    search(trimmed, 20)
      .then((response) => {
        resultsCache.set(trimmed, response);
        if (!cancelled) setResults(response);
      })
      .catch((err) => {
        console.error('Search error:', err);
        // A failed refresh keeps the results on screen
        if (!cancelled && !cached) {
          setError(apiErrorMessage(err, t, t('common.error')));
          setResults(EMPTY_RESULTS);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [debouncedQuery]);

  const setFollowed = (artistId: string, followed: boolean) => {
    const update = (r: SearchResults): SearchResults => ({
      ...r,
      artists: r.artists.map((a) => (a.id === artistId ? { ...a, followed } : a)),
    });
    setResults(update);
    const trimmed = debouncedQuery.trim();
    const cached = resultsCache.get(trimmed);
    if (cached) resultsCache.set(trimmed, update(cached));
  };

  const hasResults = results.artists.length + results.albums.length + results.songs.length > 0;
  const shows = (filter: FilterType) => activeFilter === 'all' || activeFilter === filter;

  const tabs: FilterTab<FilterType>[] = [
    { id: 'all', label: t('common.all') },
    ...(['artists', 'albums', 'songs'] as const)
      .filter((type) => results[type].length > 0)
      .map((type) => ({ id: type, label: `${t(`browse.sections.${type}`)} (${results[type].length})` })),
  ];

  return (
    <div className="space-y-8 pb-12">
      <PageHeader icon="search" title={t('nav.browse')} subtitle={t('browse.heroSubtitle')} />

      {/* Search bar, or import a playlist */}
      <div className="flex flex-col lg:flex-row items-stretch lg:items-center gap-4">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t('browse.searchInputPlaceholder')}
          size="lg"
          autoFocus
          loading={loading}
          className="flex-1"
        />

        {/* "or" separator: vertical on lg, horizontal on phones */}
        <div className="flex lg:flex-col items-center gap-3 lg:gap-1.5 lg:self-stretch">
          <div className="flex-1 lg:flex-1 h-px lg:h-auto lg:w-px bg-slate-300 dark:bg-white/10" />
          <span className="text-xs text-muted-foreground font-medium">{t('common.or')}</span>
          <div className="flex-1 lg:flex-1 h-px lg:h-auto lg:w-px bg-slate-300 dark:bg-white/10" />
        </div>

        <Link
          to="/playlist-import"
          className="flex items-center justify-center gap-2 px-5 py-4 rounded-xl glass text-foreground font-medium hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-300 whitespace-nowrap"
        >
          <Icon name="music" className="w-5 h-5 text-accent-600 dark:text-accent-400" />
          {t('playlist.importFromPlaylist')}
        </Link>
      </div>

      {error && <ErrorBanner title={t('browse.searchError')}>{error}</ErrorBanner>}

      {/* No query: recommendations, or the "start your search" box when there are none */}
      {!query.trim() && !loading && (
        <RecommendedArtists
          fallback={
            <EmptyState icon="search" title={t('browse.startSearch')}>
              <p>{t('browse.startSearchDescription')}</p>
            </EmptyState>
          }
        />
      )}

      {query.trim() && !hasResults && !loading && !error && (
        <EmptyState icon="search" title={t('browse.noResults')}>
          <p>{t('browse.noResultsFor', { query: query.trim() })}</p>
          <p className="text-sm">{t('browse.tryDifferentKeywords')}</p>
        </EmptyState>
      )}

      {hasResults && (
        <>
          <FilterTabs tabs={tabs} active={activeFilter} onChange={setActiveFilter} />

          <div className="space-y-8">
            {shows('artists') && results.artists.length > 0 && (
              <section>
                <SectionHeader>{t('browse.sections.artists')}</SectionHeader>
                {/* One sideways row: on phones a grid of big circles pushed the albums screens away.
                    pt leaves room for the cards' hover lift, which the scroller would clip */}
                <div className="flex gap-4 overflow-x-auto snap-x scroll-px-4 custom-scrollbar -mx-4 px-4 pt-2 pb-2">
                  {results.artists.map((artist) => (
                    <div key={artist.id} className="w-28 sm:w-32 lg:w-36 shrink-0 snap-start">
                      <MediaCard
                        id={artist.id}
                        title={artist.name}
                        thumbnail={getImageUrl(artist.thumbnail)}
                        type="artist"
                        to={artistPath(artist.id)}
                        artworkAction={canFollow && (
                          <QuickFollowButton
                            artistId={artist.id}
                            name={artist.name}
                            followed={artist.followed}
                            onChange={(followed) => setFollowed(artist.id, followed)}
                          />
                        )}
                      />
                    </div>
                  ))}
                </div>
              </section>
            )}

            {shows('albums') && results.albums.length > 0 && (
              <section>
                <SectionHeader>{t('browse.sections.albums')}</SectionHeader>
                <div className={MEDIA_GRID}>
                  {results.albums.map((album) => (
                    <MediaCard
                      key={album.id}
                      id={album.id}
                      title={album.title}
                      subtitle={album.artist}
                      thumbnail={getImageUrl(album.thumbnail)}
                      type="album"
                      albumType={album.type}
                      year={album.year ?? undefined}
                      subtitleTo={album.artist_id ? artistPath(album.artist_id) : undefined}
                      to={albumPath(album.id)}
                    />
                  ))}
                </div>
              </section>
            )}

            {shows('songs') && results.songs.length > 0 && (
              <section>
                <SectionHeader>{t('browse.sections.songs')}</SectionHeader>
                <div className="glass rounded-2xl overflow-hidden divide-y divide-slate-200/60 dark:divide-white/10 md:grid md:grid-cols-2 md:divide-y-0 md:gap-x-px">
                  {results.songs.map((song) => (
                    <SongRow key={song.id} song={song} />
                  ))}
                </div>
              </section>
            )}
          </div>
        </>
      )}
    </div>
  );
}
