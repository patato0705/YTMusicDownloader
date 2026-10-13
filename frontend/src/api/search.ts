// src/api/search.ts
/**
 * YouTube Music search
 */

import { api } from './client';
import type { ArtistRef } from '../types';

export interface SearchArtist {
  id: string;
  name: string;
  thumbnail: string | null;
}

export interface SearchAlbum {
  id: string;
  title: string;
  thumbnail: string | null;
  artist: string;
  artist_id: string | null;
  year: string | null;
  /** "Album", "Single", "EP" */
  type: string;
}

export interface SearchSong {
  id: string;
  title: string;
  album: { id?: string; name?: string };
  artists: ArtistRef[];
  thumbnail: string | null;
}

export interface SearchResults {
  artists: SearchArtist[];
  albums: SearchAlbum[];
  songs: SearchSong[];
}

/**
 * Artists, albums and songs matching the query, up to `limit` of each.
 * The backend caches results for 15 minutes.
 */
export async function search(query: string, limit = 10): Promise<SearchResults> {
  return api.get<SearchResults>('/search', { q: query, limit });
}
