// src/api/features.ts
/**
 * Feature flags API (any authenticated user)
 */

import { api } from './client';

export interface Features {
  charts_enabled: boolean;
  /** Lyrics are fetched with the tracks (LRCLIB) */
  lyrics_enabled: boolean;
  /** Genres are looked up on MusicBrainz / Deezer */
  genres_enabled: boolean;
}

/**
 * Which optional features are switched on. Admins change them via the
 * settings panel; everyone else only needs to read them.
 */
export async function getFeatures(): Promise<Features> {
  return api.get<Features>('/features');
}
