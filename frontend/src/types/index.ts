// src/types/index.ts

// ============================================================================
// MUSIC TYPES
// ============================================================================

export interface Thumbnail {
  url: string;
  width: number;
  height: number;
}

export interface Artist {
  id: string;
  name: string;
  thumbnail?: string;
  thumbnails?: Thumbnail[];
  image_local?: string | null;
  subscribers?: string;
  resultType?: string;
  // Library endpoint extras
  albums_count?: number;
  tracks_total?: number;
  tracks_downloaded?: number;
  followed_at?: string | null;
}

export type AlbumType = 'Album' | 'Single' | 'EP';

/** Badge shown on a MediaCard - undefined means "nothing to show" */
export type MediaStatus = 'downloaded' | 'in_library' | 'downloading' | 'queued' | undefined;

export interface Album {
  id: string;
  title: string;
  artist?: string;
  artist_id?: string;
  artist_name?: string;
  year?: string;
  type?: AlbumType | string;
  thumbnail?: string;
  thumbnails?: Thumbnail[];
  image_local?: string | null;
  playlist_id?: string;
  playlistId?: string;
  resultType?: string;
  // Library endpoint extras
  tracks_total?: number;
  tracks_downloaded?: number;
  created_at?: string | null;
}

export interface Track {
  id: string;
  title: string;
  artists?: Array<{ id: string; name: string }>;
  album?: string | { id: string; name: string } | null;
  album_id?: string;
  cover?: string | null;
  thumbnail?: string;
  thumbnails?: Thumbnail[] | null;
  duration?: number;
  duration_seconds?: number;
  track_number?: number;
  isExplicit?: boolean;
  status?: TrackStatus;
  videoId?: string;
  resultType?: string;
  raw?: any;
}

export type TrackStatus = 'new' | 'downloading' | 'done' | 'failed';

// ============================================================================
// SEARCH TYPES
// ============================================================================

export interface SearchResults {
  artists?: Artist[];
  albums?: Album[];
  tracks?: Track[];
  songs?: Track[]; // Alias for tracks
}

// ============================================================================
// UI COMPONENT TYPES
// ============================================================================

export interface FormattedMedia {
  id: string;
  title: string;
  subtitle?: string;
  thumbnail?: string;
  year?: string;
  albumType?: string;
  albumId?: string;
}
