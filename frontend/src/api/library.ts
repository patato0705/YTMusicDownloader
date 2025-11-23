// src/api/library.ts
/**
 * Library management API endpoints
 */

import { api } from './client';

export type SortOrder = 'asc' | 'desc';
export type ArtistSortBy = 'name' | 'followed_at' | 'albums_count';
export type AlbumSortBy = 'title' | 'year' | 'download_progress';
export type AlbumStatus = 'completed' | 'downloading' | 'pending' | 'failed';
export type TrackStatus = 'done' | 'failed' | 'downloading' | 'new';

export interface LibraryArtist {
  id: string;
  name: string;
  thumbnails?: any[];
  image_local?: string;
  followed_at?: string;
  albums_count?: number;
  [key: string]: any;
}

export interface LibraryAlbum {
  id: string;
  title: string;
  artist_id?: string;
  thumbnails?: any[];
  year?: string;
  type?: string;
  image_local?: string;
  download_progress?: number;
  status?: AlbumStatus;
  [key: string]: any;
}

export interface LibraryTrack {
  id: string;
  title: string;
  duration?: number;
  artists?: any[];
  album_id?: string;
  has_lyrics?: boolean;
  file_path?: string;
  status?: TrackStatus;
  created_at?: string;
  [key: string]: any;
}

export interface LibraryStats {
  followed_artists?: number;
  followed_albums?: number;
  total_tracks?: number;
  downloaded_tracks?: number;
  [key: string]: any;
}

export interface AlbumProgress {
  album: LibraryAlbum;
  tracks: LibraryTrack[];
  progress: {
    total: number;
    done: number;
    failed: number;
    downloading: number;
    pending: number;
  };
}

/**
 * List followed artists with statistics
 */
export async function getLibraryArtists(
  sortBy: ArtistSortBy = 'name',
  order: SortOrder = 'asc'
): Promise<LibraryArtist[]> {
  return api.get<LibraryArtist[]>('/library/artists', { sort_by: sortBy, order });
}

/**
 * List followed albums with download status
 */
export async function getLibraryAlbums(
  artistId?: string,
  statusFilter?: AlbumStatus,
  sortBy: AlbumSortBy = 'title',
  order: SortOrder = 'asc'
): Promise<LibraryAlbum[]> {
  const params: Record<string, any> = { sort_by: sortBy, order };
  if (artistId) params.artist_id = artistId;
  if (statusFilter) params.status_filter = statusFilter;
  
  return api.get<LibraryAlbum[]>('/library/albums', params);
}

/**
 * List tracks with optional filters
 */
export async function getLibraryTracks(
  artistId?: string,
  albumId?: string,
  statusFilter?: TrackStatus,
  hasLyrics?: boolean,
  limit = 100,
  offset = 0
): Promise<LibraryTrack[]> {
  const params: Record<string, any> = { limit, offset };
  if (artistId) params.artist_id = artistId;
  if (albumId) params.album_id = albumId;
  if (statusFilter) params.status_filter = statusFilter;
  if (hasLyrics !== undefined) params.has_lyrics = hasLyrics;
  
  return api.get<LibraryTrack[]>('/library/tracks', params);
}

/**
 * Get overall library statistics
 */
export async function getLibraryStats(): Promise<LibraryStats> {
  return api.get<LibraryStats>('/library/stats');
}

/**
 * Get detailed download progress for a specific album
 */
export async function getAlbumProgress(albumId: string): Promise<AlbumProgress> {
  return api.get<AlbumProgress>(`/library/albums/${encodeURIComponent(albumId)}/progress`);
}