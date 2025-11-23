// src/types/index.ts

// ============================================================================
// AUTH TYPES
// ============================================================================

export type UserRole = 'administrator' | 'member' | 'visitor';

export interface User {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegisterData {
  username: string;
  email: string;
  password: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

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
}

export interface ArtistDetail extends Artist {
  followed?: boolean;
}

export type AlbumType = 'Album' | 'Single' | 'EP';

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
}

export interface AlbumDetail extends Album {
  followed?: boolean;
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
// LIBRARY TYPES
// ============================================================================

export interface LibraryStats {
  artists_count?: number;
  albums_count?: number;
  tracks_count?: number;
  disk_usage_gb?: number;
}

// ============================================================================
// API RESPONSE TYPES
// ============================================================================

export interface ApiError {
  message: string;
  status?: number;
  details?: any;
}

export interface ArtistApiResponse {
  ok: boolean;
  source: string;
  followed: boolean;
  artist: Artist;
  albums: Album[];
  singles: Album[];
}

export interface AlbumApiResponse {
  source: string;
  followed: boolean;
  album: AlbumDetail;
  tracks: Track[];
}

// ============================================================================
// UI COMPONENT TYPES
// ============================================================================

export type MediaType = 'artist' | 'album' | 'track';

export interface MediaCardProps {
  id: string;
  title: string;
  subtitle?: string;
  thumbnail?: string;
  type: MediaType;
  year?: string;
  onClick?: () => void;
}

export interface FormattedMedia {
  id: string;
  title: string;
  subtitle?: string;
  thumbnail?: string;
  year?: string;
  albumId?: string;
}

// ============================================================================
// JOB TYPES
// ============================================================================

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Job {
  id: string;
  type: string;
  status: JobStatus;
  progress?: number;
  created_at: string;
  updated_at: string;
  error?: string;
}

// ============================================================================
// UTILITY TYPES
// ============================================================================

export type Nullable<T> = T | null;
export type Optional<T> = T | undefined;
export type Maybe<T> = T | null | undefined;