// src/api/tracks.ts
/**
 * Track API endpoints
 */

import { api } from './client';

export interface Track {
  id: string;
  title: string;
  duration?: number;
  artists?: any[];
  album_id?: string;
  lyrics?: 'synced' | 'plain' | null;
  file_path?: string;
  status?: string;
  created_at?: string;
  [key: string]: any;
}

export interface DownloadTrackRequest {
  video_id?: string;
  [key: string]: any;
}

export interface TrackLyrics {
  ok: boolean;
  track_id: string;
  lyrics: 'synced' | 'plain' | null;
  lyrics_local: string | null;
  /** Raw .lrc text, null when no file exists on disk */
  content: string | null;
  /** False until the audio file is downloaded (nowhere to put the .lrc yet) */
  editable: boolean;
}

export interface UpdateTrackLyricsResponse {
  ok: boolean;
  track: Track;
  content: string | null;
}

export interface MarkDoneRequest {
  file_path?: string;
  [key: string]: any;
}

export interface MarkFailedRequest {
  error?: string;
  [key: string]: any;
}

/**
 * Get track info from DB
 */
export async function getTrack(trackId: string): Promise<Track> {
  return api.get<Track>(`/tracks/${encodeURIComponent(trackId)}`);
}

/**
 * List tracks for a specific album
 */
export async function getAlbumTracks(albumId: string): Promise<Track[]> {
  return api.get<Track[]>(`/tracks/album/${encodeURIComponent(albumId)}`);
}

/**
 * Enqueue a download job for the track
 * Returns { ok: true, job_id: <int> }
 */
export async function downloadTrack(
  trackId: string,
  metadata?: DownloadTrackRequest
): Promise<any> {
  return api.post(`/tracks/${encodeURIComponent(trackId)}/download`, metadata);
}

/**
 * Fetch lyrics from LRCLIB for the track now. Bumps an already-queued
 * retry forward instead of duplicating it.
 * Returns { ok: true, job_id: <int>, queued: boolean }
 */
export async function ensureLyrics(trackId: string): Promise<{ ok: boolean; job_id: number; queued: boolean }> {
  return api.post(`/tracks/${encodeURIComponent(trackId)}/ensure_lyrics`);
}

/**
 * Read the track's .lrc file from disk
 */
export async function getTrackLyrics(trackId: string): Promise<TrackLyrics> {
  return api.get<TrackLyrics>(`/tracks/${encodeURIComponent(trackId)}/lyrics`);
}

/**
 * Overwrite the track's .lrc file. Empty content removes it and marks the
 * track as having no lyrics (the scheduler will retry LRCLIB later).
 */
export async function updateTrackLyrics(
  trackId: string,
  content: string
): Promise<UpdateTrackLyricsResponse> {
  return api.put<UpdateTrackLyricsResponse>(`/tracks/${encodeURIComponent(trackId)}/lyrics`, { content });
}

/**
 * Mark a track as done and optionally provide file_path
 */
export async function markTrackDone(
  trackId: string,
  data?: MarkDoneRequest
): Promise<any> {
  return api.post(`/tracks/${encodeURIComponent(trackId)}/mark_done`, data);
}

/**
 * Mark a track as failed with optional error message
 */
export async function markTrackFailed(
  trackId: string,
  data?: MarkFailedRequest
): Promise<any> {
  return api.post(`/tracks/${encodeURIComponent(trackId)}/mark_failed`, data);
}