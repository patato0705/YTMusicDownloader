// src/pages/Browse.tsx
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { search } from '../api/search';
import type { SearchResults } from '../api/search';
import { getImageUrl } from '../api/media';
import { MediaCard } from '../components/MediaCard';
import { RecommendedArtists } from '../components/RecommendedArtists';
import { SearchInput } from '../components/ui/SearchInput';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import { FilterTabs } from '../components/ui/FilterTabs';
import type { FilterTab } from '../components/ui/FilterTabs';
import { EmptyState, ErrorBanner } from '../components/ui/PageStatus';
import { apiErrorMessage, createMemoryCache } from '../utils';
import { useDebounce } from '../hooks/useDebounce';

const VALID_FILTERS = ['all', 'artists', 'albums', 'songs'] as const;
type FilterType = typeof VALID_FILTERS[number];

const EMPTY_RESULTS: SearchResults = { artists: [], albums: [], songs: [] };

/** Results by query: coming back to a search shows them right away */
const resultsCache = createMemoryCache<SearchResults>(20);

const GRID = 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4';

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
  const navigate = useNavigate();
  const { t } = useI18n();

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

    const cached = trimmed ? resultsCache.get(trimmed) : EMPTY_RESULTS;
    if (cached) {
      setResults(cached);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);

    search(trimmed, 20)
      .then((response) => {
        resultsCache.set(trimmed, response);
        if (!cancelled) setResults(response);
      })
      .catch((err) => {
        console.error('Search error:', err);
        if (!cancelled) {
          setError(apiErrorMessage(err, t, t('common.error')));
          setResults(EMPTY_RESULTS);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [debouncedQuery]);

  // The artist named under an album / song opens that artist, when YTM gave its id
  const openArtist = (artistId?: string | null): (() => void) | undefined =>
    artistId ? () => navigate(`/artists/${encodeURIComponent(artistId)}`) : undefined;

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
      <PageHero
        title={
          <>
            <span className="text-foreground">{t('browse.heroDiscover')} </span>
            <span className="text-gradient">{t('browse.heroNewMusic')}</span>
          </>
        }
        subtitle={t('browse.heroSubtitle')}
      />

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
          <svg className="w-5 h-5 text-blue-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
          </svg>
          {t('playlist.importFromPlaylist')}
        </Link>
      </div>

      {error && <ErrorBanner title={t('browse.searchError')}>{error}</ErrorBanner>}

      {/* No query: recommendations, or the "start your search" box when there are none */}
      {!query.trim() && !loading && (
        <RecommendedArtists
          fallback={
            <EmptyState icon="🔍" title={t('browse.startSearch')}>
              <p>{t('browse.startSearchDescription')}</p>
            </EmptyState>
          }
        />
      )}

      {query.trim() && !hasResults && !loading && !error && (
        <EmptyState icon="😔" title={t('browse.noResults')}>
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
                <div className={GRID}>
                  {results.artists.map((artist) => (
                    <MediaCard
                      key={artist.id}
                      id={artist.id}
                      title={artist.name}
                      thumbnail={getImageUrl(artist.thumbnail)}
                      type="artist"
                      onClick={() => navigate(`/artists/${encodeURIComponent(artist.id)}`)}
                    />
                  ))}
                </div>
              </section>
            )}

            {shows('albums') && results.albums.length > 0 && (
              <section>
                <SectionHeader>{t('browse.sections.albums')}</SectionHeader>
                <div className={GRID}>
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
                      onSubtitleClick={openArtist(album.artist_id)}
                      onClick={() => navigate(`/albums/${encodeURIComponent(album.id)}`)}
                    />
                  ))}
                </div>
              </section>
            )}

            {shows('songs') && results.songs.length > 0 && (
              <section>
                <SectionHeader>{t('browse.sections.songs')}</SectionHeader>
                <div className={GRID}>
                  {results.songs.map((song) => (
                    <MediaCard
                      key={song.id}
                      id={song.id}
                      title={song.title}
                      subtitle={song.artists[0]?.name ?? undefined}
                      thumbnail={getImageUrl(song.thumbnail)}
                      type="track"
                      onSubtitleClick={openArtist(song.artists[0]?.id)}
                      onClick={() => {
                        if (song.album.id) navigate(`/albums/${encodeURIComponent(song.album.id)}`);
                      }}
                    />
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
