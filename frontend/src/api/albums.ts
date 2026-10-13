// src/api/albums.ts
/**
 * Album API endpoints
 */

import { api } from './client';
import type { AlbumMode, ArtistRef, Track } from '../types';

export interface AlbumDetails {
  id: string;
  title: string;
  artist: ArtistRef | null;
  year: string | null;
  type: string;
  /** Cover on disk, or YouTube Music's for an album not in the library */
  thumbnail: string | null;
  genres: string[];
}

export interface AlbumPage {
  /**
   * "database" when the page follows the job queue (a download-mode album,
   * even one whose tracks still come from YouTube Music); "ytmusic" otherwise
   */
  source: 'database' | 'ytmusic';
  mode: AlbumMode | null;
  /** A download-mode album without tracks and with no import waiting: Retry imports it again */
  needs_import: boolean;
  album: AlbumDetails;
  tracks: Track[];
}

/**
 * An album and its tracks: from the DB when its tracks are there, otherwise
 * from YouTube Music
 */
export async function getAlbum(albumId: string): Promise<AlbumPage> {
  return api.get<AlbumPage>(`/albums/${encodeURIComponent(albumId)}`);
}

/**
 * Download an album: sets it to download mode and queues its import, which
 * refreshes the tracklist and queues a download for every track not on disk.
 * `artist_subscription_created`: its artist was added to the library (light).
 */
export async function downloadAlbum(albumId: string): Promise<{ started: boolean; artist_subscription_created: boolean }> {
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
