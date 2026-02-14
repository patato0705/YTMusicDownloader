// src/pages/Browse.tsx
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { search } from '../api/index';
import { getImageUrl } from '../api/media';
import MediaCard from '../components/MediaCard';
import { SearchInput } from '../components/ui/SearchInput';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import { useDebounce } from '../hooks';
import {
  formatArtist,
  formatAlbum,
  formatTrack,
  normalizeSearchResults,
  filterAlbums,
} from '../utils';
import type { SearchResults } from '../types';

export default function Browse(): JSX.Element {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResults>({
    artists: [],
    albums: [],
    tracks: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<'all' | 'artists' | 'albums' | 'tracks'>('all');
  const navigate = useNavigate();
  const { t } = useI18n();

  // Debounce search query
  const debouncedQuery = useDebounce(query, 500);

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

        {/* Search bar */}
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder="Search for artists, albums, or tracks..."
          size="lg"
          autoFocus
          loading={loading}
          className="max-w-4xl mx-auto"
        />

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