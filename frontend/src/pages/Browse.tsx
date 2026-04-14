// src/pages/Browse.tsx
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { search } from '../api/index';
import { getImageUrl } from '../api/media';
import MediaCard from '../components/MediaCard';
import { SearchInput } from '../components/ui/SearchInput';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import {
  formatArtist,
  formatAlbum,
  formatTrack,
  normalizeSearchResults,
  filterAlbums,
} from '../utils';
import type { SearchResults } from '../types';

/**
 * Debounce hook - delays updating a value until after a specified delay
 */
function useDebounce<T>(value: T, delay: number = 500): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

const VALID_FILTERS = ['all', 'artists', 'albums', 'tracks'] as const;
type FilterType = typeof VALID_FILTERS[number];

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
      if (newFilter && newFilter !== 'all') {
        next.set('filter', newFilter);
      } else {
        next.delete('filter');
      }
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const [results, setResults] = useState<SearchResults>({
    artists: [],
    albums: [],
    tracks: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { t } = useI18n();

  // Debounce search query
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

  // Trigger search when debounced query changes
  useEffect(() => {
    const trimmed = debouncedQuery.trim();

    if (!trimmed) {
      setResults({ artists: [], albums: [], tracks: [] });
      setError(null);
      setLoading(false);
      return;
    }

    performSearch(trimmed);
  }, [debouncedQuery]);

  const performSearch = async (searchQuery: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await search(searchQuery, 20);
      const normalized = normalizeSearchResults(response);
      setResults(normalized);
    } catch (err: any) {
      console.error('Search error:', err);
      setError(err.message || t('common.error'));
      setResults({ artists: [], albums: [], tracks: [] });
    } finally {
      setLoading(false);
    }
  };

  const hasResults =
    (results.artists?.length || 0) +
    (results.albums?.length || 0) +
    (results.tracks?.length || 0) > 0;

  // Filter results based on active filter
  const filteredResults = {
    artists: activeFilter === 'all' || activeFilter === 'artists' ? results.artists : [],
    albums: activeFilter === 'all' || activeFilter === 'albums' ? results.albums : [],
    tracks: activeFilter === 'all' || activeFilter === 'tracks' ? results.tracks : [],
  };

  return (
    <div className="relative min-h-screen">
      {/* Background effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
      
      {/* Main content */}
      <div className="relative z-10 space-y-8 pb-12">
        {/* Hero section */}
        <PageHero
          title={
            <>
              <span className="text-foreground">Discover </span>
              <span className="text-gradient">New Music</span>
            </>
          }
          subtitle="Search YouTube Music for artists, albums, and tracks to add to your library"
        />

        {/* Search bar + Import playlist */}
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center gap-4">
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="Search for artists, albums, or tracks..."
            size="lg"
            autoFocus
            loading={loading}
            className="flex-1"
          />

          {/* "or" separator — vertical on lg, horizontal on mobile */}
          <div className="flex lg:flex-col items-center gap-3 lg:gap-1.5 lg:self-stretch">
            <div className="flex-1 lg:flex-1 h-px lg:h-auto lg:w-px bg-slate-300 dark:bg-white/10" />
            <span className="text-xs text-muted-foreground font-medium">{t('common.or')}</span>
            <div className="flex-1 lg:flex-1 h-px lg:h-auto lg:w-px bg-slate-300 dark:bg-white/10" />
          </div>

          <Link
            to="/playlist-import"
            className="flex items-center justify-center gap-2 px-5 py-4 rounded-xl glass border border-slate-200 dark:border-white/10 text-foreground font-medium hover:bg-slate-100 dark:hover:bg-white/10 transition-all duration-300 whitespace-nowrap"
          >
            <svg className="w-5 h-5 text-blue-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
            </svg>
            {t('playlist.importFromPlaylist')}
          </Link>
        </div>

        {/* Error message */}
        {error && (
          <div className="bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl p-6 border border-red-500/20">
            <div className="flex items-center gap-3">
              <span className="text-2xl">⚠️</span>
              <div>
                <h3 className="font-semibold text-red-600 dark:text-red-400 mb-1">
                  Search Error
                </h3>
                <p className="text-sm text-red-600/80 dark:text-red-400/80">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Empty state - No query */}
        {!query.trim() && !loading && (
          <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-16 border border-slate-200/50 dark:border-white/10 text-center">
            <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-6">
              <span className="text-5xl">🔍</span>
            </div>
            <h3 className="text-2xl font-bold mb-3">Start Your Search</h3>
            <p className="text-muted-foreground max-w-md mx-auto">
              Enter an artist name, album title, or song to discover new music from YouTube Music
            </p>
          </div>
        )}

        {/* Empty state - No results */}
        {query.trim() && !hasResults && !loading && !error && (
          <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-16 border border-slate-200/50 dark:border-white/10 text-center">
            <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-6">
              <span className="text-5xl">😔</span>
            </div>
            <h3 className="text-2xl font-bold mb-3">No Results Found</h3>
            <p className="text-muted-foreground max-w-md mx-auto mb-6">
              We couldn't find anything matching <span className="font-semibold text-foreground">"{query}"</span>
            </p>
            <p className="text-sm text-muted-foreground">
              Try different keywords or check your spelling
            </p>
          </div>
        )}

        {/* Results - Show filter tabs when there are results */}
        {hasResults && (
          <>
            {/* Filter tabs */}
            <div className="flex items-center gap-2 glass rounded-2xl p-2 w-fit">
              <button
                onClick={() => setActiveFilter('all')}
                className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                  activeFilter === 'all'
                    ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                    : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                }`}
              >
                All
              </button>
              {results.artists && results.artists.length > 0 && (
                <button
                  onClick={() => setActiveFilter('artists')}
                  className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                    activeFilter === 'artists'
                      ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                      : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                  }`}
                >
                  Artists ({results.artists.length})
                </button>
              )}
              {results.albums && results.albums.length > 0 && (
                <button
                  onClick={() => setActiveFilter('albums')}
                  className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                    activeFilter === 'albums'
                      ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                      : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                  }`}
                >
                  Albums ({results.albums.length})
                </button>
              )}
              {results.tracks && results.tracks.length > 0 && (
                <button
                  onClick={() => setActiveFilter('tracks')}
                  className={`px-4 py-2 rounded-xl font-medium transition-all duration-300 ${
                    activeFilter === 'tracks'
                      ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                      : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
                  }`}
                >
                  Tracks ({results.tracks.length})
                </button>
              )}
            </div>

            {/* Results sections */}
            <div className="space-y-8">
              {/* Artists */}
              {filteredResults.artists && filteredResults.artists.length > 0 && (
                <section>
                  <SectionHeader>Artists</SectionHeader>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                    {filteredResults.artists.map((artist) => {
                      const formatted = formatArtist(artist);
                      return (
                        <MediaCard
                          key={formatted.id}
                          id={formatted.id}
                          title={formatted.title}
                          subtitle={formatted.subtitle}
                          thumbnail={getImageUrl(formatted.thumbnail)}
                          type="artist"
                          onClick={() => navigate(`/artists/${encodeURIComponent(formatted.id)}`)}
                        />
                      );
                    })}
                  </div>
                </section>
              )}

              {/* Albums */}
              {filteredResults.albums && filteredResults.albums.length > 0 && (
                <section>
                  <SectionHeader>Albums</SectionHeader>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                    {filterAlbums(filteredResults.albums).map((album) => {
                      const formatted = formatAlbum(album);
                      return (
                        <MediaCard
                          key={formatted.id}
                          id={formatted.id}
                          title={formatted.title}
                          subtitle={formatted.subtitle}
                          thumbnail={getImageUrl(formatted.thumbnail)}
                          type="album"
                          year={formatted.year}
                          onClick={() => navigate(`/albums/${encodeURIComponent(formatted.id)}`)}
                        />
                      );
                    })}
                  </div>
                </section>
              )}

              {/* Tracks */}
              {filteredResults.tracks && filteredResults.tracks.length > 0 && (
                <section>
                  <SectionHeader>Tracks</SectionHeader>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                    {filteredResults.tracks.map((track) => {
                      const formatted = formatTrack(track);
                      return (
                        <MediaCard
                          key={formatted.id}
                          id={formatted.id}
                          title={formatted.title}
                          subtitle={formatted.subtitle}
                          thumbnail={getImageUrl(formatted.thumbnail)}
                          type="track"
                          onClick={() => {
                            if (formatted.albumId) {
                              navigate(`/albums/${encodeURIComponent(formatted.albumId)}`);
                            }
                          }}
                        />
                      );
                    })}
                  </div>
                </section>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}