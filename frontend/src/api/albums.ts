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
  followed?: boolean;
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
 * Follow an album
 * 1. Fetch album from YTMusic if not in DB
 * 2. Create album subscription
 * 3. Queue download jobs for all tracks
 */
export async function followAlbum(albumId: string): Promise<any> {
  return api.post(`/albums/${encodeURIComponent(albumId)}/follow`);
}

/**
 * Unfollow an album
 * Removes album subscription but doesn't delete data or cancel jobs
 */
export async function unfollowAlbum(albumId: string): Promise<any> {
  return api.delete(`/albums/${encodeURIComponent(albumId)}/follow`);
}