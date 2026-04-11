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
 * Download an album
 * 1. Fetch album from YTMusic if not in DB
 * 2. Set album mode to "download"
 * 3. Queue download jobs for all tracks
 */
export async function downloadAlbum(albumId: string): Promise<any> {
  return api.post(`/albums/${encodeURIComponent(albumId)}/download`);
}

/**
 * Cancel album download
 * Reverts album to metadata mode; does not delete data or files
 */
export async function cancelAlbumDownload(albumId: string): Promise<any> {
  return api.delete(`/albums/${encodeURIComponent(albumId)}/download`);
}