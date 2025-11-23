// src/pages/Browse.tsx
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { search } from '../api/index';
import MediaCard from '../components/MediaCard';
import { Spinner } from '../components/ui/Spinner';
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
  const navigate = useNavigate();
  const { t } = useI18n();

  // Debounce search query
  const debouncedQuery = useDebounce(query, 300);

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
      const response = await search(searchQuery, 10);
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed) {
      performSearch(trimmed);
    }
  };

  const hasResults =
    (results.artists?.length || 0) +
    (results.albums?.length || 0) +
    (results.tracks?.length || 0) > 0;

  return (
    <div>
      <h1 className="text-3xl font-bold text-foreground mb-6">
        {t('browse.title')}
      </h1>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="mb-8">
        <div className="max-w-3xl">
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('browse.searchPlaceholder')}
              className="flex-1 rounded-lg border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
            />
            <button
              type="submit"
              className="px-6 py-3 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-semibold transition disabled:opacity-50"
              disabled={loading}
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <Spinner size="sm" />
                  <span>{t('browse.searching')}</span>
                </div>
              ) : (
                t('common.search')
              )}
            </button>
          </div>
        </div>
      </form>

      {/* Error message */}
      {error && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500 text-red-600 dark:text-red-400 rounded-lg">
          {t('common.error')}: {error}
        </div>
      )}

      {/* Empty states */}
      {!query.trim() && !loading && (
        <div className="text-center py-12">
          <div className="text-6xl mb-4">🔍</div>
          <p className="text-muted-foreground">{t('browse.noQuery')}</p>
        </div>
      )}

      {query.trim() && !hasResults && !loading && (
        <div className="text-center py-12">
          <div className="text-6xl mb-4">😔</div>
          <p className="text-muted-foreground">{t('browse.noResults')}</p>
        </div>
      )}

      {/* Results sections */}
      <div className="space-y-8">
        {/* Artists */}
        {results.artists && results.artists.length > 0 && (
          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">
              {t('browse.sections.artists')}
            </h2>
            <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-thin">
              {results.artists.map((artist) => {
                const formatted = formatArtist(artist);
                return (
                  <MediaCard
                    key={formatted.id}
                    id={formatted.id}
                    title={formatted.title}
                    subtitle={formatted.subtitle}
                    thumbnail={formatted.thumbnail}
                    type="artist"
                    onClick={() => navigate(`/artists/${encodeURIComponent(formatted.id)}`)}
                  />
                );
              })}
            </div>
          </section>
        )}

        {/* Albums */}
        {results.albums && results.albums.length > 0 && (
          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">
              {t('browse.sections.albums')}
            </h2>
            <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-thin">
              {filterAlbums(results.albums).map((album) => {
                const formatted = formatAlbum(album);
                return (
                  <MediaCard
                    key={formatted.id}
                    id={formatted.id}
                    title={formatted.title}
                    subtitle={formatted.subtitle}
                    thumbnail={formatted.thumbnail}
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
        {results.tracks && results.tracks.length > 0 && (
          <section>
            <h2 className="text-2xl font-semibold text-foreground mb-4">
              {t('browse.sections.tracks')}
            </h2>
            <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-thin">
              {results.tracks.map((track) => {
                const formatted = formatTrack(track);
                return (
                  <MediaCard
                    key={formatted.id}
                    id={formatted.id}
                    title={formatted.title}
                    subtitle={formatted.subtitle}
                    thumbnail={formatted.thumbnail}
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
    </div>
  );
}