// src/types/index.ts
/**
 * Shapes shared by several endpoints. Types used by a single endpoint live
 * next to its call in src/api/.
 */

/** An artist named on a track or an album; YouTube Music doesn't always give the id */
export interface ArtistRef {
  id: string | null;
  name: string | null;
}

/** Badge shown on a MediaCard; undefined means "nothing to show" */
export type MediaStatus = 'downloaded' | 'in_library' | 'downloading' | 'queued' | 'failed' | undefined;

/**
 * Download state of a track in the DB (backend/services/tracks.py):
 * available = nothing planned, queued = a download job is waiting for it
 * (incl. retries and rate-limit pauses), failed = out of attempts.
 * Tracks served straight from YTMusic have none.
 */
export type TrackStatus = 'available' | 'queued' | 'downloading' | 'done' | 'failed';

/** What kind of .lrc a downloaded track has on disk; null = none yet */
export type LyricsKind = 'synced' | 'plain' | null;

/** Album download state (backend/services/subscriptions.py), null for albums not being downloaded */
export type AlbumDownloadStatus = 'completed' | 'downloading' | 'pending' | 'failed' | 'idle' | null;

/** How an album is kept: its music downloaded, or only its metadata (from a followed artist's light sync) */
export type AlbumMode = 'download' | 'metadata';

/** How an artist is followed: in full (every release downloaded), or light (metadata only) */
export type SubscriptionMode = 'full' | 'light';

/**
 * A track of an album page (Track.to_dict). Those served from YouTube Music
 * (album not imported yet) have no download state.
 */
export interface Track {
  id: string;
  title: string;
  artists: ArtistRef[];
  track_number: number | null;
  /** Seconds */
  duration: number | null;
  album_id?: string;
  status?: TrackStatus;
  last_error?: string | null;
  lyrics?: LyricsKind;
  lyrics_local?: string | null;
}
