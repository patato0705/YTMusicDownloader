// src/api/albums.ts
/**
 * Album API endpoints
 */

import { api } from './client';

export interface Album {
  id: string;
  title: string;
  artist_id?: string;
  thumbnails?: any[];
  playlist_id?: string;
  year?: string;
  type?: string;
  image_local?: string;
  tracks?: any[];
  mode?: string | null;
  [key: string]: any;
}

/**
 * Get album details
 * Tries DB first, then fetches from YTMusic if not found
 */
export async function getAlbum(albumId: string): Promise<Album> {
  return api.get<Album>(`/albums/${encodeURIComponent(albumId)}`);
}

/**
 * Download an album: sets it to download mode and queues its import,
 * which refreshes the tracklist and queues a download for every track
 * not on disk (an album not in the DB yet is fetched first)
 */
export async function downloadAlbum(albumId: string): Promise<any> {
  return api.post(`/albums/${encodeURIComponent(albumId)}/download`);
}

/**
 * Requeue the tracks of a downloaded album that aren't on disk
 * (failed ones, and any left without a job), or its import when it has
 * no tracks at all (import_queued)
 */
export async function retryAlbum(albumId: string): Promise<{ album_id: string; tracks_queued: number; import_queued: boolean }> {
  return api.post(`/albums/${encodeURIComponent(albumId)}/retry`);
}

/**
 * Cancel album download
 * Reverts album to metadata mode; does not delete data or files
 */
export async function cancelAlbumDownload(albumId: string): Promise<any> {
  return api.delete(`/albums/${encodeURIComponent(albumId)}/download`);
}