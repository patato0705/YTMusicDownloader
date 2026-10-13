// src/api/tracks.ts
/**
 * Track lyrics (.lrc files next to the audio)
 */

import { api } from './client';
import type { LyricsKind, Track } from '../types';

export interface TrackLyrics {
  track_id: string;
  lyrics: LyricsKind;
  lyrics_local: string | null;
  /** Raw .lrc text, null when no file exists on disk */
  content: string | null;
  /** False until the audio file is downloaded (nowhere to put the .lrc yet) */
  editable: boolean;
}

export interface UpdateTrackLyricsResponse {
  track: Track;
  content: string | null;
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
