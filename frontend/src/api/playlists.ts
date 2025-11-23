// src/api/playlists.ts
/**
 * Playlist API endpoints
 */

import { api } from './client';

export interface Playlist {
  id: string;
  title?: string;
  thumbnails?: any[];
  tracks?: any[];
  [key: string]: any;
}

export interface PlaylistAlbum {
  id: string;
  title: string;
  artist_id?: string;
  [key: string]: any;
}

/**
 * Get playlist details with track/album info
 * Use this to extract album IDs from playlists for bulk following
 * Playlists are not saved to library
 */
export async function getPlaylist(playlistId: string): Promise<Playlist> {
  return api.get<Playlist>(`/playlists/${encodeURIComponent(playlistId)}`);
}

/**
 * Extract unique album IDs from a playlist
 * Returns list of albums for bulk operations
 */
export async function extractAlbumsFromPlaylist(playlistId: string): Promise<PlaylistAlbum[]> {
  return api.get<PlaylistAlbum[]>(`/playlists/${encodeURIComponent(playlistId)}/albums`);
}