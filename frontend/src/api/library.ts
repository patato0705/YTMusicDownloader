// src/api/library.ts
/**
 * Library management API endpoints
 */

import { api } from './client';

export type SortOrder = 'asc' | 'desc';
export type ArtistSortBy = 'name' | 'followed_at' | 'albums_count';
export type AlbumSortBy = 'title' | 'year' | 'download_progress' | 'followed_at';
export type AlbumStatus = 'completed' | 'downloading' | 'pending' | 'failed';
export type TrackStatus = 'done' | 'failed' | 'downloading' | 'new';

export interface LibraryArtist {
  id: string;
  name: string;
  thumbnail?: string | null;
  thumbnails?: any[];
  image_local?: string;
  followed_at?: string;
  albums_count?: number;
  tracks_total?: number;
  tracks_downloaded?: number;
  tracks_failed?: number;
  download_progress?: number;
  last_synced_at?: string;
  [key: string]: any;
}

export interface LibraryAlbum {
  id: string;
  title: string;
  artist?: {
    id: string;
    name: string;
  };
  artist_id?: string;
  artist_name?: string;
  thumbnail?: string;
  thumbnails?: any[];
  year?: string;
  type?: string;
  image_local?: string;
  download_status?: AlbumStatus;
  download_progress?: number;
  status?: AlbumStatus;
  tracks_total?: number;
  tracks_downloaded?: number;
  tracks_failed?: number;
  tracks_with_lyrics?: number;
  followed_at?: string;
  [key: string]: any;
}

export interface LibraryTrack {
  id: string;
  title: string;
  duration?: number;
  artists?: any[];
  album?: {
    id: string;
    title: string;
    thumbnail?: string;
  };
  artist?: {
    id: string;
    name: string;
  };
  album_id?: string;
  has_lyrics?: boolean;
  lyrics_path?: string | null;
  file_path?: string;
  status?: TrackStatus;
  created_at?: string;
  [key: string]: any;
}

export interface LibraryStats {
  artists?: {
    total: number;
  };
  albums?: {
    total: number;
    completed: number;
    downloading: number;
    pending: number;
    failed: number;
  };
  tracks?: {
    total: number;
    downloaded: number;
    downloading: number;
    pending: number;
    failed: number;
    with_lyrics: number;
  };
  storage?: {
    estimated_mb: number;
    estimated_gb: number;
  };
  [key: string]: any;
}

export interface AlbumProgress {
  album: LibraryAlbum;
  tracks: LibraryTrack[];
  subscription?: {
    status: string;
    followed_at: string;
  };
  progress: {
    percentage: number;
    tracks_total: number;
    tracks_downloaded: number;
    tracks_downloading: number;
    tracks_failed: number;
    tracks_pending: number;
    tracks_with_lyrics: number;
  };
}

export interface ArtistsResponse {
  artists: LibraryArtist[];
  total: number;
}

export interface AlbumsResponse {
  albums: LibraryAlbum[];
  total: number;
}

export interface TracksResponse {
  tracks: LibraryTrack[];
  total: number;
  limit: number;
  offset: number;
}

export interface GetLibraryAlbumsParams {
  artist_id?: string;
  status_filter?: AlbumStatus;
  sort_by?: AlbumSortBy;
  order?: SortOrder;
  limit?: number;
  offset?: number;
}

/**
 * List followed artists with statistics
 */
export async function getLibraryArtists(
  sortBy: ArtistSortBy = 'name',
  order: SortOrder = 'asc'
): Promise<ArtistsResponse> {
  return api.get<ArtistsResponse>('/library/artists', { sort_by: sortBy, order });
}

/**
 * List followed albums with download status
 */
export async function getLibraryAlbums(
  params?: GetLibraryAlbumsParams
): Promise<AlbumsResponse> {
  const queryParams: Record<string, any> = {
    sort_by: params?.sort_by || 'title',
    order: params?.order || 'asc'
  };
  
  if (params?.artist_id) queryParams.artist_id = params.artist_id;
  if (params?.status_filter) queryParams.status_filter = params.status_filter;
  if (params?.limit) queryParams.limit = params.limit;
  if (params?.offset) queryParams.offset = params.offset;
  
  return api.get<AlbumsResponse>('/library/albums', queryParams);
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
): Promise<TracksResponse> {
  const params: Record<string, any> = { limit, offset };
  if (artistId) params.artist_id = artistId;
  if (albumId) params.album_id = albumId;
  if (statusFilter) params.status_filter = statusFilter;
  if (hasLyrics !== undefined) params.has_lyrics = hasLyrics;
  
  return api.get<TracksResponse>('/library/tracks', params);
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