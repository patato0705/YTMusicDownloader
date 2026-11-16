// src/api/library.ts
/**
 * Library management API endpoints
 */

import { api } from './client';
import type { AlbumDownloadStatus, AlbumMode, ArtistRef, LyricsKind, SubscriptionMode, TrackStatus } from '../types';

export type SortOrder = 'asc' | 'desc';
/** queue: the order the download worker will reach each album, those with nothing waiting last */
export type AlbumSortBy = 'title' | 'year' | 'created_at' | 'download_progress' | 'queue';

export interface LibraryArtist {
  id: string;
  name: string;
  thumbnail: string | null;
  genres: string[];
  /** Genres were looked up (an empty list then means none were found) */
  genres_checked: boolean;
  mode: SubscriptionMode;
  /** Followed by a chart, which may unfollow it */
  chart_followed: boolean;
  /** Whether you like it */
  liked: boolean;
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
  /** Downloaded tracks without lyrics */
  tracks_missing_lyrics: number;
  /** Downloaded tracks whose lyrics aren't synced */
  tracks_plain_lyrics: number;
  genres: string[];
  /** Genres were looked up (an empty list then means none were found) */
  genres_checked: boolean;
  /** A playlist (in albums mode) lists one of its songs */
  from_playlist: boolean;
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
    /** LRCLIB lists them as instrumental: no lyrics to fetch */
    instrumental: number;
  };
  storage: { bytes: number; gb: number };
}

export interface GetLibraryAlbumsParams {
  sort_by?: AlbumSortBy;
  order?: SortOrder;
  limit?: number;
  /** Only albums in one of these download states */
  statuses?: Array<'completed' | 'downloading' | 'pending' | 'failed'>;
}

/**
 * Why nothing automatic (charts, playlists, artist syncs, backups) brings
 * an artist or album back: deleted from the library, or (an artist)
 * unfollowed. Following or downloading it by hand lifts that.
 */
export type ExclusionReason = 'deleted' | 'unfollowed' | 'artist_deleted';

export interface ExcludedArtist {
  id: string;
  name: string;
  /** Its picture, while it's still in the library (an unfollowed one) */
  thumbnail: string | null;
  reason: ExclusionReason;
  excluded_at: string;
}

export interface ExcludedAlbum {
  id: string;
  title: string;
  artist: { id: string; name: string | null } | null;
  thumbnail: string | null;
  year: string | null;
  type: string;
  reason: ExclusionReason;
  excluded_at: string;
}

export interface Exclusions {
  artists: ExcludedArtist[];
  albums: ExcludedAlbum[];
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
export async function getLibraryAlbums({ statuses, ...params }: GetLibraryAlbumsParams = {}): Promise<LibraryAlbum[]> {
  const query = statuses ? { ...params, status_filter: statuses.join(',') } : params;
  return (await api.get<{ albums: LibraryAlbum[] }>('/library/albums', query)).albums;
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

/** The artists and albums kept out of the library, newest first */
export async function getExclusions(): Promise<Exclusions> {
  return api.get<Exclusions>('/library/exclusions');
}

/** Let charts, playlists and syncs bring it in again (nothing is followed or downloaded here) */
export async function restoreExclusion(kind: 'artist' | 'album', id: string): Promise<void> {
  await api.delete(`/library/exclusions/${kind}/${encodeURIComponent(id)}`);
}
