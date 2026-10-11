// src/api/recommendations.ts
/**
 * Artist recommendations: YouTube Music's similar artists of the artists
 * you follow, ranked by how many of them point to each.
 */

import { api } from './client';

export interface RecommendedArtist {
  id: string;
  name: string;
  thumbnail: string | null;
  /** How many followed artists it's similar to */
  count: number;
  /** Those followed artists, most similar first */
  similar_to: { id: string; name: string }[];
}

export interface DismissedArtist {
  id: string;
  name: string;
  thumbnail: string | null;
  dismissed_at: string | null;
}

export async function getRecommendations(): Promise<{
  recommendations: RecommendedArtist[];
  dismissed_count: number;
}> {
  return api.get('/recommendations');
}

export async function getDismissedArtists(): Promise<{ dismissed: DismissedArtist[] }> {
  return api.get('/recommendations/dismissed');
}

/** "Not interested": never recommended again, until restored */
export async function dismissArtist(artistId: string): Promise<void> {
  await api.put(`/recommendations/dismissed/${encodeURIComponent(artistId)}`);
}

export async function restoreArtist(artistId: string): Promise<void> {
  await api.delete(`/recommendations/dismissed/${encodeURIComponent(artistId)}`);
}
