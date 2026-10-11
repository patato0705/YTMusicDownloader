// src/api/playlists.ts
/**
 * Playlist API endpoints
 */

import { api } from './client';

export interface PlaylistTrack {
  id: string;
  title: string;
  artists: Array<{ id: string | null; name: string | null }>;
  album: { id: string | null; name: string | null } | null;
  cover?: string | null;
  duration_seconds: number;
  track_number?: number | null;
  isExplicit?: boolean;
}

export type PlaylistMode = 'albums' | 'artists';

/** A playlist added to the library (backend/services/playlists.py) */
export interface SavedPlaylist {
  id: string;
  title: string;
  author: string | null;
  thumbnail: string | null;
  /** What its songs bring in: their albums, or their main artists (followed in full) */
  mode: PlaylistMode;
  /** Rescanned on the schedule; otherwise kept as added */
  followed: boolean;
  m3u: boolean;
  /** Path of the M3U file in the music folder */
  m3u_file: string | null;
  songs: number;
  /** Songs that bring nothing in: no album (music videos, uploads) */
  skipped: number;
  /** Songs found in the library */
  available: number;
  /** A scan is waiting or running */
  syncing: boolean;
  last_synced_at: string | null;
  last_error: string | null;
  created_at: string | null;
}

export interface PlaylistOptions {
  mode: PlaylistMode;
  followed: boolean;
  m3u: boolean;
}

export interface Playlist {
  id: string;
  title?: string;
  description?: string | null;
  author?: string | null;
  thumbnail?: string | null;
  tracks: PlaylistTrack[];
  /** How it's added to the library, null if it isn't */
  saved: SavedPlaylist | null;
  /** Its artists already followed, and its albums already downloaded */
  followed_artists: string[];
  downloaded_albums: string[];
}

/** A playlist from YouTube Music with its tracks, and how it's added to the library */
export async function getPlaylist(playlistId: string): Promise<Playlist> {
  return api.get<Playlist>(`/playlists/${encodeURIComponent(playlistId)}`);
}

export async function listPlaylists(): Promise<SavedPlaylist[]> {
  return (await api.get<{ playlists: SavedPlaylist[] }>('/playlists')).playlists;
}

export async function addPlaylist(playlistId: string, options: PlaylistOptions): Promise<SavedPlaylist> {
  return api.post<SavedPlaylist>(`/playlists/${encodeURIComponent(playlistId)}`, options);
}

export async function updatePlaylist(playlistId: string, options: Partial<PlaylistOptions>): Promise<SavedPlaylist> {
  return api.patch<SavedPlaylist>(`/playlists/${encodeURIComponent(playlistId)}`, options);
}

/** Rescan a followed playlist now */
export async function syncPlaylist(playlistId: string): Promise<SavedPlaylist> {
  return api.post<SavedPlaylist>(`/playlists/${encodeURIComponent(playlistId)}/sync`);
}

/** Remove it from the library, with its M3U; the music stays */
export async function removePlaylist(playlistId: string): Promise<void> {
  await api.delete(`/playlists/${encodeURIComponent(playlistId)}`);
}
