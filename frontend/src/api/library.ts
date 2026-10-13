// src/api/library.ts
/**
 * Library management API endpoints
 */

import { api } from './client';
import type { AlbumDownloadStatus, AlbumMode, ArtistRef, LyricsKind, SubscriptionMode, TrackStatus } from '../types';

export type SortOrder = 'asc' | 'desc';
export type AlbumSortBy = 'title' | 'year' | 'created_at' | 'download_progress';

export interface LibraryArtist {
  id: string;
  name: string;
  thumbnail: string | null;
  mode: SubscriptionMode;
  followed_at: string | null;
  albums_count: number;
  tracks_total: number;
  tracks_downloaded: number;
  tracks_failed: number;
  download_progress: number;
  last_synced_at: string | null;
}

export interface LibraryAlbum {
  id: string;
  title: string;
  artist: { id: string; name: string } | null;
  year: string | null;
  type: string;
  mode: AlbumMode;
  thumbnail: string | null;
  download_status: AlbumDownloadStatus;
  tracks_total: number;
  tracks_downloaded: number;
  tracks_failed: number;
  tracks_with_lyrics: number;
  download_progress: number;
  created_at: string | null;
}

export interface LibraryTrack {
  id: string;
  title: string;
  artists: ArtistRef[];
  album: { id: string; title: string; thumbnail: string | null };
  artist: { id: string; name: string } | null;
  duration: number | null;
  status: TrackStatus;
  lyrics: LyricsKind;
  created_at: string | null;
}

export interface LibraryStats {
  artists: { total: number };
  /** total: every album row (metadata ones included); downloaded: those in the library (download mode) */
  albums: {
    total: number;
    downloaded: number;
    completed: number;
    downloading: number;
    pending: number;
    failed: number;
  };
  tracks: {
    total: number;
    downloaded: number;
    downloading: number;
    pending: number;
    failed: number;
    with_lyrics: number;
    with_synced_lyrics: number;
    with_plain_lyrics: number;
  };
  storage: { bytes: number; gb: number };
}

export interface GetLibraryAlbumsParams {
  sort_by?: AlbumSortBy;
  order?: SortOrder;
  limit?: number;
}

/** What deleting an album or artist also changes, for its confirmation dialog */
export interface DeletionEffects {
  /** The album's followed artist, switched to light so the album isn't downloaded again */
  artist_unfollowed?: { id: string; name: string | null } | null;
  /** Followed playlists that would bring it back, unfollowed */
  playlists_unfollowed: { id: string; title: string }[];
}

/**
 * Followed artists with their download counts, by name
 */
export async function getLibraryArtists(): Promise<LibraryArtist[]> {
  return (await api.get<{ artists: LibraryArtist[] }>('/library/artists')).artists;
}

/**
 * Albums in the library (download mode) with their download state
 */
export async function getLibraryAlbums(params: GetLibraryAlbumsParams = {}): Promise<LibraryAlbum[]> {
  return (await api.get<{ albums: LibraryAlbum[] }>('/library/albums', params)).albums;
}

/**
 * Library tracks whose title contains the query (case-insensitive)
 */
export async function searchLibraryTracks(query: string, limit = 200): Promise<LibraryTrack[]> {
  return (await api.get<{ tracks: LibraryTrack[] }>('/library/tracks', { q: query, limit })).tracks;
}

/**
 * Overall library statistics
 */
export async function getLibraryStats(): Promise<LibraryStats> {
  return api.get<LibraryStats>('/library/stats');
}

/**
 * Delete an artist and all associated albums, tracks, files, and subscriptions (admin only)
 */
export async function deleteLibraryArtist(artistId: string): Promise<void> {
  await api.delete(`/library/artists/${encodeURIComponent(artistId)}`);
}

/**
 * Delete an album and all associated tracks and files (admin only)
 */
export async function deleteLibraryAlbum(albumId: string): Promise<void> {
  await api.delete(`/library/albums/${encodeURIComponent(albumId)}`);
}

export async function getAlbumDeletionEffects(albumId: string): Promise<DeletionEffects> {
  return api.get(`/library/albums/${encodeURIComponent(albumId)}/deletion`);
}

export async function getArtistDeletionEffects(artistId: string): Promise<DeletionEffects> {
  return api.get(`/library/artists/${encodeURIComponent(artistId)}/deletion`);
}
