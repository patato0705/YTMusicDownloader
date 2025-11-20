// Helper functions to format data for MediaCard component

export interface MediaCardData {
  id: string;
  title: string;
  subtitle?: string;
  thumbnail?: string | null;
  type?: "artist" | "album" | "track";
}

/**
 * Format artist data for MediaCard
 */
export function formatArtist(artist: any): MediaCardData {
  return {
    id: artist.id || "",
    title: artist.name || artist.title || "Artiste inconnu",
    subtitle: "", // Artists don't have subtitles
    thumbnail: artist.thumbnail || null,
    type: "artist",
  };
}

/**
 * Format album data for MediaCard
 */
export function formatAlbum(album: any): MediaCardData {
  const artist = album.artist || "";
  const year = album.year || "";
  
  let subtitle = "";
  if (artist && year) {
    subtitle = `${artist} • ${year}`;
  } else if (artist) {
    subtitle = artist;
  } else if (year) {
    subtitle = year;
  }

  return {
    id: album.id || album.browseId || "",
    title: album.title || album.name || "Album sans titre",
    subtitle,
    thumbnail: album.thumbnail || album.image || null,
    type: "album",
  };
}

/**
 * Format track/song data for MediaCard
 */
export function formatTrack(track: any): MediaCardData {
  // Build artist string
  let artistStr = "";
  if (Array.isArray(track.artists)) {
    artistStr = track.artists
      .map((a: any) => (typeof a === "string" ? a : a?.name || ""))
      .filter(Boolean)
      .join(", ");
  } else if (track.artist) {
    artistStr = track.artist;
  }

  // Build album string
  const albumName = track.album?.name || track.album?.title || "";

  // Combine: "Artist • Album"
  let subtitle = "";
  if (artistStr && albumName) {
    subtitle = `${artistStr} • ${albumName}`;
  } else if (artistStr) {
    subtitle = artistStr;
  } else if (albumName) {
    subtitle = albumName;
  }

  return {
    id: track.id || track.videoId || "",
    title: track.title || track.name || "Titre inconnu",
    subtitle,
    thumbnail: track.thumbnail || null,
    type: "track",
  };
}

/**
 * Auto-detect and format any media item
 */
export function formatMediaItem(item: any): MediaCardData {
  const type = (item.resultType || item.type || "").toLowerCase();
  
  if (type === "artist") {
    return formatArtist(item);
  } else if (type === "album") {
    return formatAlbum(item);
  } else if (type === "song" || type === "track") {
    return formatTrack(item);
  }
  
  // Fallback: try to detect from fields
  if (item.artists || item.album) {
    return formatTrack(item);
  } else if (item.browseId || item.year) {
    return formatAlbum(item);
  }
  
  return formatArtist(item);
}