// src/api/search.ts
/**
 * Search API endpoints
 */

import { api } from './client';

export interface SearchResults {
  artists?: any[];
  albums?: any[];
  songs?: any[];
}

export interface ChartResults {
  artists?: any[];
  songs?: any[];
}

/**
 * Search all types (artists, albums, songs)
 * Uses filtered searches for more reliable results
 * Results are cached for 15 minutes
 */
export async function search(query: string, limit = 10): Promise<SearchResults> {
  return api.get<SearchResults>('/search', { q: query, limit });
}

/**
 * Search for artists only
 */
export async function searchArtists(query: string, limit = 10): Promise<any[]> {
  return api.get<any[]>('/search/artists', { q: query, limit });
}

/**
 * Search for albums only
 */
export async function searchAlbums(query: string, limit = 10): Promise<any[]> {
  return api.get<any[]>('/search/albums', { q: query, limit });
}

/**
 * Search for songs only
 */
export async function searchSongs(query: string, limit = 10): Promise<any[]> {
  return api.get<any[]>('/search/songs', { q: query, limit });
}

/**
 * Get music charts for a country
 * Returns top artists and songs
 * Results are cached for 15 minutes
 */
export async function getCharts(country = 'US'): Promise<ChartResults> {
  return api.get<ChartResults>('/search/charts', { country });
}

/**
 * Clear the search cache (admin only)
 */
export async function clearSearchCache(): Promise<void> {
  return api.delete('/search/cache');
}