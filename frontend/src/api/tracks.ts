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
  has_lyrics?: boolean;
  file_path?: string;
  status?: string;
  created_at?: string;
  [key: string]: any;
}

export interface DownloadTrackRequest {
  video_id?: string;
  [key: string]: any;
}

export interface EnsureLyricsRequest {
  artists?: string[];
  title?: string;
  album?: string;
  duration?: number;
  dest_audio_path?: string;
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
 * Enqueue a job to fetch synchronized lyrics for the track
 * Returns { ok: true, job_id: <int> }
 */
export async function ensureLyrics(
  trackId: string,
  metadata?: EnsureLyricsRequest
): Promise<any> {
  return api.post(`/tracks/${encodeURIComponent(trackId)}/ensure_lyrics`, metadata);
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