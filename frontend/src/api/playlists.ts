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

export interface Playlist {
  id: string;
  title?: string;
  description?: string | null;
  author?: string | null;
  thumbnail?: string | null;
  tracks: PlaylistTrack[];
}

/**
 * Get playlist details with track/album info
 * Use this to extract album IDs from playlists for bulk following
 * Playlists are not saved to library
 */
export async function getPlaylist(playlistId: string): Promise<Playlist> {
  return api.get<Playlist>(`/playlists/${encodeURIComponent(playlistId)}`);
}
