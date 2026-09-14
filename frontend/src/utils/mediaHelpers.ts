// src/utils/mediaHelpers.ts
import type { Artist, Album, Track, FormattedMedia, MediaStatus, Thumbnail } from '../types';

/**
 * Extracts the best quality thumbnail from various possible formats
 */
function getBestThumbnail(
  item: any,
  preferredSize: 'small' | 'medium' | 'large' = 'medium'
): string {
  if (!item) return '';

  // Check for image_local first (locally cached image - best quality)
  if (item.image_local && typeof item.image_local === 'string') {
    return item.image_local;
  }

  // Check for direct thumbnail URL
  if (item.thumbnail && typeof item.thumbnail === 'string') {
    return item.thumbnail;
  }

  // Check for direct image property
  if (item.image && typeof item.image === 'string') {
    return item.image;
  }

  // Check for cover property (used in some track responses)
  if (item.cover && typeof item.cover === 'string') {
    return item.cover;
  }

  // Check thumbnails array
  if (Array.isArray(item.thumbnails) && item.thumbnails.length > 0) {
    const thumbnails = item.thumbnails as Thumbnail[];
    
    // Sort by size (width)
    const sorted = [...thumbnails].sort((a, b) => (b.width || 0) - (a.width || 0));
    
    if (preferredSize === 'large') {
      return sorted[0]?.url || '';
    } else if (preferredSize === 'small') {
      return sorted[sorted.length - 1]?.url || '';
    } else {
      // Medium - try to get middle size
      const midIndex = Math.floor(sorted.length / 2);
      return sorted[midIndex]?.url || sorted[0]?.url || '';
    }
  }

  // No thumbnail found - return empty string (let image onError handle it)
  return '';
}

/**
 * Formats an artist object from various API response formats
 */
export function formatArtist(item: any): FormattedMedia {
  return {
    id: item.id || item.browseId || '',
    title: item.name || item.title || 'Unknown Artist',
    subtitle: item.subscribers || '',
    thumbnail: getBestThumbnail(item),
  };
}

/**
 * Formats an album object from various API response formats
 */
export function formatAlbum(item: any): FormattedMedia {
  // Extract artist name from various possible locations
  const artistName = 
    item.artist_name || 
    item.artist?.name || 
    item.artists?.[0]?.name || 
    item.artist ||
    '';

  return {
    id: item.id || item.browseId || '',
    title: item.title || 'Unknown Album',
    subtitle: artistName,
    thumbnail: getBestThumbnail(item),
    year: item.year || '',
    albumType: item.type || item.album_type || '',
  };
}

/**
 * Formats a track/song object from various API response formats
 */
export function formatTrack(item: any): FormattedMedia {
  // Extract artist name
  const artistName = 
    item.artists?.[0]?.name || 
    item.artist?.name || 
    item.artist ||
    '';

  // Extract album ID
  const albumId = 
    item.album?.id || 
    item.album_id || 
    '';

  return {
    id: item.id || item.videoId || '',
    title: item.title || 'Unknown Track',
    subtitle: artistName,
    thumbnail: getBestThumbnail(item, 'small'),
    albumId,
  };
}

/**
 * Normalizes search results from various backend response formats
 * Handles both grouped objects and flat arrays
 */
export function normalizeSearchResults(raw: any): {
  artists: Artist[];
  albums: Album[];
  tracks: Track[];
} {
  const result = {
    artists: [] as Artist[],
    albums: [] as Album[],
    tracks: [] as Track[],
  };

  if (!raw) return result;

  // Handle grouped object response (preferred format)
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const artists = raw.artists ?? raw.artists_list ?? raw.artist ?? [];
    const albums = raw.albums ?? raw.albums_list ?? raw.album ?? [];
    const tracks = raw.tracks ?? raw.songs ?? raw.songs_list ?? raw.track ?? [];

    if (Array.isArray(artists) || Array.isArray(albums) || Array.isArray(tracks)) {
      result.artists = Array.isArray(artists) ? artists : [];
      result.albums = Array.isArray(albums) ? albums : [];
      result.tracks = Array.isArray(tracks) ? tracks : [];
      return result;
    }
  }

  // Handle flat array response - categorize by type
  const list = Array.isArray(raw) ? raw : [];

  for (const item of list) {
    if (!item || typeof item !== 'object') continue;

    // Extract type from various possible locations
    const typeRaw =
      item.resultType ?? 
      item.type ?? 
      item.result_type ?? 
      item.raw?.resultType ?? 
      item.raw?.type ?? 
      '';
    
    const type = String(typeRaw).toLowerCase();

    // Categorize by explicit type
    if (type === 'artist') {
      result.artists.push(item);
    } else if (type === 'album') {
      result.albums.push(item);
    } else if (type === 'song' || type === 'track') {
      result.tracks.push(item);
    } else {
      // Fallback: Use heuristics for uncategorized items
      if (item.videoId || item.duration || item.duration_seconds) {
        // Looks like a track
        result.tracks.push(item);
      } else if (item.browseId && String(item.browseId).startsWith('MPRE')) {
        // Looks like an album (browseId starting with MPRE)
        result.albums.push(item);
      } else if (item.artists || item.artist || item.subscribers) {
        // Looks like an artist
        result.artists.push(item);
      }
    }
  }

  return result;
}

/**
 * Filters out playlists and mixes from album results
 */
export function filterAlbums(albums: Album[]): Album[] {
  return albums.filter((album) => {
    const type = (album.type ?? album.resultType ?? '').toString().toLowerCase();
    return !type.includes('playlist') && !type.includes('mix');
  });
}

/**
 * Badge to show on an album card.
 * Handles both payload shapes: the artist endpoint reports `download_status`,
 * the library endpoint reports track counts.
 */
export function getAlbumStatus(album: any): MediaStatus {
  if (!album) return undefined;

  if (album.download_status === 'downloading') return 'downloading';

  // "pending" means tracks are queued with none being fetched right now. That
  // is also what the worker reports in the gap between two tracks of the same
  // album - and refreshes land precisely on those gaps, since they're triggered
  // by a job finishing. So an album with tracks already on disk and more to go
  // keeps the spinner; only one that hasn't started shows as queued.
  if (album.download_status === 'pending') {
    const total = album.tracks_total ?? 0;
    const downloaded = album.tracks_downloaded ?? 0;
    return downloaded > 0 && downloaded < total ? 'downloading' : 'queued';
  }

  // Nothing left to try and at least one track didn't make it
  if (album.download_status === 'failed') return 'failed';

  // Metadata-only albums are never downloaded, and unsynced ones have no state yet
  if (album.mode === 'metadata') return undefined;
  if (!album.image_local && album.tracks_total == null && !album.in_database) return undefined;

  if (album.download_status === 'completed') return 'downloaded';

  const total = album.tracks_total ?? 0;
  const downloaded = album.tracks_downloaded ?? 0;
  if (total > 0 && downloaded >= total) return 'downloaded';

  return 'in_library';
}

/**
 * Badge to show on a followed artist card. The artist payload carries aggregated
 * track counts; `albums` (when available) tells us whether a download is running.
 */
export function getArtistStatus(artist: any, albums: any[] = []): MediaStatus {
  if (!artist) return undefined;

  const albumStatuses = albums
    .filter((album) => (album.artist?.id ?? album.artist_id) === artist.id)
    .map(getAlbumStatus);
  if (albumStatuses.includes('downloading')) return 'downloading';
  if (albumStatuses.includes('queued')) return 'queued';
  // The artist payload carries its own failed count, for pages without the album list
  if (albumStatuses.includes('failed') || (artist.tracks_failed ?? 0) > 0) return 'failed';

  const total = artist.tracks_total ?? 0;
  const downloaded = artist.tracks_downloaded ?? 0;
  if (total > 0 && downloaded >= total) return 'downloaded';

  return 'in_library';
}

/**
 * Separates albums from singles/EPs
 */
export function categorizeAlbums(albums: Album[]): {
  albums: Album[];
  singles: Album[];
} {
  const regularAlbums = albums.filter(
    (a) => a.type?.toLowerCase() === 'album' || !a.type
  );
  
  const singles = albums.filter((a) =>
    ['single', 'ep'].includes(a.type?.toLowerCase() || '')
  );

  return { albums: regularAlbums, singles };
}

/**
 * Gets the primary artist from a track
 */
export function getPrimaryArtist(track: Track): string {
  if (Array.isArray(track.artists) && track.artists.length > 0) {
    return track.artists[0].name;
  }
  return 'Unknown Artist';
}

/**
 * Formats duration from seconds to MM:SS format
 */
export function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds < 0) return '--:--';
  
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Formats duration from seconds to human-readable format (e.g., "3h 24m")
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
