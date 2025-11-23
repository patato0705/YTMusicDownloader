// src/api/artists.ts
/**
 * Artist API endpoints
 */

import { api } from './client';

export interface Artist {
  id: string;
  name: string;
  thumbnails?: any[];
  image_local?: string;
  followed?: boolean;
  created_at?: string;
  albums?: any[];
  [key: string]: any;
}

/**
 * Get artist info
 * Tries DB first, then fetches from YTMusic if not found
 */
export async function getArtist(artistId: string): Promise<Artist> {
  return api.get<Artist>(`/artists/${encodeURIComponent(artistId)}`);
}

/**
 * Follow an artist
 * 1. Fetch artist data from YTMusic (includes albums/singles list)
 * 2. Fetch and upsert ALL albums/singles with their tracks
 * 3. Mark artist as followed
 * 4. Create artist subscription
 * 5. Create album subscriptions for all albums
 * 6. Queue download jobs for all tracks
 * 
 * This can take 15-35 seconds depending on number of albums
 */
export async function followArtist(artistId: string): Promise<any> {
  return api.post(`/artists/${encodeURIComponent(artistId)}/follow`);
}

/**
 * Unfollow an artist
 * Marks artist as not followed and removes subscriptions
 * Does NOT delete data or cancel jobs
 */
export async function unfollowArtist(artistId: string): Promise<any> {
  return api.delete(`/artists/${encodeURIComponent(artistId)}/follow`);
}