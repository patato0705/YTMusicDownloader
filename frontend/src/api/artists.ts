// src/api/artists.ts
/**
 * Artist API endpoints
 */

import { api } from './client';
import type { AlbumDownloadStatus, AlbumMode, SubscriptionMode } from '../types';

export interface ArtistRelease {
  id: string;
  title: string;
  /** "Album", "Single", "EP" */
  type: string;
  year: string | null;
  thumbnail: string | null;
  /** Whether the album has a row in the DB, and what it knows of it */
  in_database: boolean;
  mode: AlbumMode | null;
  download_status: AlbumDownloadStatus;
}

export interface ArtistPage {
  /** "database" for an artist followed in full (refreshed with the job queue), "ytmusic" otherwise */
  source: 'database' | 'ytmusic';
  subscription_mode: SubscriptionMode | null;
  /** Whether you like it (only artists of the library, subscription_mode set, can be) */
  liked: boolean;
  artist: {
    id: string;
    name: string;
    thumbnail: string | null;
    genres: string[];
  };
  albums: ArtistRelease[];
}

/**
 * An artist and its releases: from the DB for an artist followed in full,
 * otherwise from YouTube Music
 */
export async function getArtist(artistId: string): Promise<ArtistPage> {
  return api.get<ArtistPage>(`/artists/${encodeURIComponent(artistId)}`);
}

/**
 * Follow an artist in full: every release is downloaded, and you like it.
 * Returns at once; a sync job fetches the artist and its releases. `name`
 * is shown for it in the library until then.
 */
export async function followArtist(artistId: string, name: string): Promise<void> {
  await api.post(`/artists/${encodeURIComponent(artistId)}/follow`, { name });
}

/**
 * Unfollow an artist: back to a light subscription, its albums to metadata
 * and their pending downloads cancelled. Files stay.
 */
export async function unfollowArtist(artistId: string): Promise<void> {
  await api.delete(`/artists/${encodeURIComponent(artistId)}/follow`);
}

/** Like an artist of the library: its similar artists join your recommendations */
export async function likeArtist(artistId: string): Promise<void> {
  await api.put(`/artists/${encodeURIComponent(artistId)}/like`);
}

export async function unlikeArtist(artistId: string): Promise<void> {
  await api.delete(`/artists/${encodeURIComponent(artistId)}/like`);
}

/** Like or unlike, as `liked` says */
export async function setArtistLiked(artistId: string, liked: boolean): Promise<void> {
  await (liked ? likeArtist(artistId) : unlikeArtist(artistId));
}
