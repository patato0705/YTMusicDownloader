// src/utils/mediaHelpers.ts
import type { AlbumDownloadStatus, AlbumMode, ArtistRef, MediaStatus } from '../types';
import type { LibraryAlbum, LibraryArtist } from '../api/library';

/** What an album's badge is worked out from: the library's albums and the artist page's releases */
interface AlbumState {
  mode: AlbumMode | null;
  download_status: AlbumDownloadStatus;
  tracks_total?: number;
  tracks_downloaded?: number;
  /** False for a release only known from YouTube Music */
  in_database?: boolean;
}

/**
 * Badge to show on an album card.
 */
export function getAlbumStatus(album: AlbumState): MediaStatus {
  // Not in the DB, or only its metadata: nothing is downloaded
  if (album.in_database === false || album.mode !== 'download') return undefined;

  switch (album.download_status) {
    case 'downloading':
      return 'downloading';
    case 'pending': {
      // "pending" means tracks are queued with none being fetched right now.
      // That is also what the worker reports in the gap between two tracks of
      // the same album, and refreshes land precisely on those gaps, since
      // they're triggered by a job finishing. So an album with tracks already
      // on disk and more to go keeps the spinner; only one that hasn't
      // started shows as queued. The artist page has no track counts: queued.
      const total = album.tracks_total ?? 0;
      const downloaded = album.tracks_downloaded ?? 0;
      return downloaded > 0 && downloaded < total ? 'downloading' : 'queued';
    }
    // Nothing left to try and at least one track didn't make it
    case 'failed':
      return 'failed';
    case 'completed':
      return 'downloaded';
    default:
      return 'in_library';
  }
}

/**
 * Badge to show on a followed artist card: a download running for one of its
 * albums, otherwise its track counts.
 */
export function getArtistStatus(artist: LibraryArtist, albums: LibraryAlbum[] = []): MediaStatus {
  const albumStatuses = albums.map(getAlbumStatus);
  if (albumStatuses.includes('downloading')) return 'downloading';
  if (albumStatuses.includes('queued')) return 'queued';
  if (albumStatuses.includes('failed') || artist.tracks_failed > 0) return 'failed';

  if (artist.tracks_total > 0 && artist.tracks_downloaded >= artist.tracks_total) return 'downloaded';
  return 'in_library';
}

/**
 * Separates singles and EPs from albums. Any other release type (a
 * compilation, something YouTube Music adds later) is listed with the albums.
 */
export function categorizeAlbums<T extends { type: string }>(releases: T[]): { albums: T[]; singles: T[] } {
  const isSingle = (release: T) => ['single', 'ep'].includes(release.type.toLowerCase());
  return {
    albums: releases.filter((release) => !isSingle(release)),
    singles: releases.filter(isSingle),
  };
}

/** Name of a track's main artist; '' when YouTube Music gave none */
export function primaryArtistName(track: { artists: ArtistRef[] }): string {
  return track.artists[0]?.name ?? '';
}

/**
 * Formats duration from seconds to M:SS format
 */
export function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds < 0) return '--:--';

  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);

  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Formats duration from seconds to a short readable form (e.g. "3h 24m")
 */
export function formatDurationLong(seconds?: number | null): string {
  if (!seconds || seconds < 0) return '0 min';

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }

  return `${minutes} min`;
}
