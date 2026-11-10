// src/utils/libraryFilters.ts
/**
 * The Library page's filters and sort, worked out in the browser: the page
 * already holds every followed artist and album.
 *
 * Each filter group picks values: an item matches a group when it matches
 * any of its picked values, and the filters when it matches every group.
 *
 * Groups apply at one of three levels:
 * - album groups (downloads, lyrics, type, decade, genre, source) test an
 *   album; an artist matches them when one of its albums matches all of them
 *   at once ("singles missing lyrics" means one single missing lyrics)
 * - artist groups (liked, follow) test an artist; an album matches them
 *   through its artist
 * - item groups (metadata) test each artist and album on its own data
 */
import type { LibraryAlbum, LibraryArtist, SortOrder } from '../api/library';
import type { MediaStatus } from '../types';

export const FILTER_GROUPS = ['downloads', 'lyrics', 'metadata', 'type', 'decade', 'genre', 'source', 'follow', 'liked'] as const;
export type FilterGroup = typeof FILTER_GROUPS[number];

/** Picked values by group; a group left out (or empty) lets everything through */
export type LibraryFilters = Partial<Record<FilterGroup, string[]>>;

/** The values of the groups that don't depend on what the library holds */
export const FIXED_OPTIONS: Partial<Record<FilterGroup, readonly string[]>> = {
  downloads: ['missing', 'failed', 'active'],
  lyrics: ['missing', 'plain'],
  metadata: ['artwork', 'genre'],
  type: ['album', 'single', 'ep'],
  source: ['artist', 'playlist', 'own'],
  follow: ['full', 'light'],
  liked: ['liked'],
};

const ALBUM_GROUPS: readonly FilterGroup[] = ['downloads', 'lyrics', 'type', 'decade', 'genre', 'source'];
const ARTIST_GROUPS: readonly FilterGroup[] = ['follow', 'liked'];

/** The decade value of an album without a year */
export const UNKNOWN_DECADE = 'unknown';

/** What the tests need beyond the item itself */
export interface FilterContext {
  artistById: Map<string, LibraryArtist>;
  albumsByArtist: Map<string, LibraryAlbum[]>;
  albumStatus: Map<string, MediaStatus>;
}

// ============================================================================
// VALUES OF AN ITEM
// ============================================================================

/** Album, single or EP: any other release type is listed with the albums (see albumTypeKey) */
export function releaseKind(type: string | null | undefined): 'album' | 'single' | 'ep' {
  const kind = type?.trim().toLowerCase();
  return kind === 'single' || kind === 'ep' ? kind : 'album';
}

function yearOf(year: string | null | undefined): number | null {
  const parsed = parseInt(year ?? '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

/** "1990" for 1994, UNKNOWN_DECADE without a year */
export function decadeOf(year: string | null | undefined): string {
  const parsed = yearOf(year);
  return parsed === null ? UNKNOWN_DECADE : String(Math.floor(parsed / 10) * 10);
}

/** The followed artist of an album, if it is one */
function albumArtist(album: LibraryAlbum, ctx: FilterContext): LibraryArtist | undefined {
  return album.artist?.id ? ctx.artistById.get(album.artist.id) : undefined;
}

// ============================================================================
// TESTS
// ============================================================================

function albumTest(group: FilterGroup, value: string, album: LibraryAlbum, ctx: FilterContext): boolean {
  switch (group) {
    case 'downloads': {
      if (value === 'missing') return album.tracks_downloaded < album.tracks_total;
      const status = ctx.albumStatus.get(album.id);
      if (value === 'failed') return album.tracks_failed > 0 || status === 'failed';
      return status === 'downloading' || status === 'queued';
    }
    case 'lyrics':
      return value === 'missing' ? album.tracks_missing_lyrics > 0 : album.tracks_plain_lyrics > 0;
    case 'type':
      return releaseKind(album.type) === value;
    case 'decade':
      return decadeOf(album.year) === value;
    case 'genre':
      return album.genres.includes(value);
    case 'source': {
      const byArtist = albumArtist(album, ctx)?.mode === 'full';
      if (value === 'artist') return byArtist;
      if (value === 'playlist') return album.from_playlist;
      return !byArtist && !album.from_playlist;
    }
    default:
      return false;
  }
}

function artistTest(group: FilterGroup, value: string, artist: LibraryArtist): boolean {
  return group === 'liked' ? artist.liked : artist.mode === value;
}

function metadataTest(value: string, item: { thumbnail: string | null; genres: string[]; genres_checked: boolean }): boolean {
  return value === 'artwork' ? !item.thumbnail : item.genres_checked && item.genres.length === 0;
}

const picked = (filters: LibraryFilters, group: FilterGroup): string[] => filters[group] ?? [];

function passesAlbumGroups(album: LibraryAlbum, filters: LibraryFilters, ctx: FilterContext): boolean {
  return ALBUM_GROUPS.every((group) => {
    const values = picked(filters, group);
    return values.length === 0 || values.some((value) => albumTest(group, value, album, ctx));
  });
}

function passesArtistGroups(artist: LibraryArtist | undefined, filters: LibraryFilters): boolean {
  return ARTIST_GROUPS.every((group) => {
    const values = picked(filters, group);
    return values.length === 0 || (!!artist && values.some((value) => artistTest(group, value, artist)));
  });
}

function passesMetadata(item: Parameters<typeof metadataTest>[1], filters: LibraryFilters): boolean {
  const values = picked(filters, 'metadata');
  return values.length === 0 || values.some((value) => metadataTest(value, item));
}

export function albumMatches(album: LibraryAlbum, filters: LibraryFilters, ctx: FilterContext): boolean {
  return passesMetadata(album, filters)
    && passesArtistGroups(albumArtist(album, ctx), filters)
    && passesAlbumGroups(album, filters, ctx);
}

const hasAlbumGroups = (filters: LibraryFilters) => ALBUM_GROUPS.some((group) => picked(filters, group).length > 0);

/** The artist's albums matching every album group at once: all of them when none is picked */
function matchingAlbums(artist: LibraryArtist, filters: LibraryFilters, ctx: FilterContext): LibraryAlbum[] {
  const albums = ctx.albumsByArtist.get(artist.id) ?? [];
  return hasAlbumGroups(filters) ? albums.filter((album) => passesAlbumGroups(album, filters, ctx)) : albums;
}

export function artistMatches(artist: LibraryArtist, filters: LibraryFilters, ctx: FilterContext): boolean {
  if (!passesMetadata(artist, filters) || !passesArtistGroups(artist, filters)) return false;
  if (!hasAlbumGroups(filters)) return true;
  return (ctx.albumsByArtist.get(artist.id) ?? []).some((album) => passesAlbumGroups(album, filters, ctx));
}

export function activeFilterCount(filters: LibraryFilters): number {
  return FILTER_GROUPS.reduce((sum, group) => sum + picked(filters, group).length, 0);
}

/** Picks or unpicks one value */
export function toggleFilter(filters: LibraryFilters, group: FilterGroup, value: string): LibraryFilters {
  const values = picked(filters, group);
  const next = values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
  const { [group]: _removed, ...rest } = filters;
  return next.length > 0 ? { ...rest, [group]: next } : rest;
}

// ============================================================================
// OPTIONS AND THEIR COUNTS
// ============================================================================

export interface FilterOptionCount {
  value: string;
  /** Results with this value picked in its group, the other groups as they are */
  count: number;
  /** Items in the whole library that have it: an option no item has is left out */
  libraryCount: number;
}

export interface FilterGroupCounts {
  group: FilterGroup;
  options: FilterOptionCount[];
}

export interface FilterItems {
  artists: LibraryArtist[];
  albums: LibraryAlbum[];
}

function withoutGroup(filters: LibraryFilters, group: FilterGroup): LibraryFilters {
  const { [group]: _omitted, ...rest } = filters;
  return rest;
}

/**
 * How many results each value of one group gives, the other groups as they
 * are. The items passing the other groups are found once, then each value is
 * tested on those alone: hundreds of genres don't each rerun every filter.
 */
function countGroupValues(
  items: FilterItems,
  filters: LibraryFilters,
  ctx: FilterContext,
  group: FilterGroup,
  values: readonly string[],
): Map<string, number> {
  const rest = withoutGroup(filters, group);
  const albums = items.albums.filter((album) => albumMatches(album, rest, ctx));
  const counts = new Map<string, number>();

  if (ALBUM_GROUPS.includes(group)) {
    // An artist counts when one of its albums passing the other album groups has the value
    const artistAlbums = items.artists
      .filter((artist) => passesMetadata(artist, rest) && passesArtistGroups(artist, rest))
      .map((artist) => matchingAlbums(artist, rest, ctx));
    for (const value of values) {
      let count = 0;
      for (const album of albums) if (albumTest(group, value, album, ctx)) count++;
      for (const candidates of artistAlbums) if (candidates.some((album) => albumTest(group, value, album, ctx))) count++;
      counts.set(value, count);
    }
    return counts;
  }

  // Artist groups test an album's artist; metadata tests each item on its own
  const artists = items.artists.filter((artist) => artistMatches(artist, rest, ctx));
  const testArtist = (value: string, artist: LibraryArtist | undefined) =>
    !!artist && (group === 'metadata' ? metadataTest(value, artist) : artistTest(group, value, artist));
  const testAlbum = (value: string, album: LibraryAlbum) =>
    group === 'metadata' ? metadataTest(value, album) : testArtist(value, albumArtist(album, ctx));
  for (const value of values) {
    let count = 0;
    for (const album of albums) if (testAlbum(value, album)) count++;
    for (const artist of artists) if (testArtist(value, artist)) count++;
    counts.set(value, count);
  }
  return counts;
}

/** Genres by how many albums have them, then by name */
function genreValues(albums: LibraryAlbum[], collator: Intl.Collator): string[] {
  const counts = new Map<string, number>();
  for (const album of albums) for (const genre of album.genres) counts.set(genre, (counts.get(genre) ?? 0) + 1);
  return [...counts.keys()].sort((a, b) => counts.get(b)! - counts.get(a)! || collator.compare(a, b));
}

/** Newest decade first, albums without a year last */
function decadeValues(albums: LibraryAlbum[]): string[] {
  const decades = new Set(albums.map((album) => decadeOf(album.year)));
  const known = [...decades].filter((d) => d !== UNKNOWN_DECADE).sort((a, b) => Number(b) - Number(a));
  return decades.has(UNKNOWN_DECADE) ? [...known, UNKNOWN_DECADE] : known;
}

/** Each option's items in the whole library, in display order: they only change with the library */
export type LibraryOptionCounts = Map<FilterGroup, Map<string, number>>;

export interface OfferedFilters {
  groups: readonly FilterGroup[];
  /** Genres are looked up, so "No genre found" means something */
  genresLookedUp: boolean;
}

export function libraryOptionCounts(
  library: FilterItems,
  ctx: FilterContext,
  offered: OfferedFilters,
  collator: Intl.Collator,
): LibraryOptionCounts {
  return new Map(offered.groups.map((group) => {
    let values: readonly string[] = group === 'genre'
      ? genreValues(library.albums, collator)
      : group === 'decade'
        ? decadeValues(library.albums)
        : FIXED_OPTIONS[group] ?? [];
    if (group === 'metadata' && !offered.genresLookedUp) values = values.filter((value) => value !== 'genre');
    return [group, countGroupValues(library, {}, ctx, group, values)];
  }));
}

/**
 * Every group's options with their counts, for the filter panel.
 *
 * `shown`: the items the page could list right now (tab and search applied)
 * `library`: from libraryOptionCounts, for the groups to offer
 */
export function filterCounts(
  shown: FilterItems,
  library: LibraryOptionCounts,
  filters: LibraryFilters,
  ctx: FilterContext,
): FilterGroupCounts[] {
  return [...library].map(([group, libraryCounts]) => {
    const values = [...libraryCounts.keys()];
    // Picked values the library doesn't have (an old link) stay, so they can be removed
    for (const value of picked(filters, group)) if (!values.includes(value)) values.push(value);

    const counts = countGroupValues(shown, filters, ctx, group, values);
    const options = values.map((value) => ({
      value,
      count: counts.get(value) ?? 0,
      libraryCount: libraryCounts.get(value) ?? 0,
    }));
    return { group, options };
  });
}

// ============================================================================
// WHY AN ITEM IS LISTED
// ============================================================================

export type FilterHint =
  | { key: 'missingTracks'; count: number; total: number }
  | { key: 'failedTracks'; count: number }
  | { key: 'missingLyrics'; count: number }
  | { key: 'plainLyrics'; count: number }
  | { key: 'noArtwork' }
  | { key: 'noGenre' };

interface TrackCounts {
  tracks_total: number;
  tracks_downloaded: number;
  tracks_failed: number;
  tracks_missing_lyrics: number;
  tracks_plain_lyrics: number;
}

function sumCounts(albums: LibraryAlbum[]): TrackCounts {
  const sum: TrackCounts = { tracks_total: 0, tracks_downloaded: 0, tracks_failed: 0, tracks_missing_lyrics: 0, tracks_plain_lyrics: 0 };
  for (const album of albums) {
    sum.tracks_total += album.tracks_total;
    sum.tracks_downloaded += album.tracks_downloaded;
    sum.tracks_failed += album.tracks_failed;
    sum.tracks_missing_lyrics += album.tracks_missing_lyrics;
    sum.tracks_plain_lyrics += album.tracks_plain_lyrics;
  }
  return sum;
}

function hints(
  counts: TrackCounts,
  item: Parameters<typeof metadataTest>[1],
  filters: LibraryFilters,
): FilterHint[] {
  const result: FilterHint[] = [];
  const downloads = picked(filters, 'downloads');
  const lyrics = picked(filters, 'lyrics');
  const metadata = picked(filters, 'metadata');
  const missing = counts.tracks_total - counts.tracks_downloaded;

  if (downloads.includes('missing') && missing > 0) {
    result.push({ key: 'missingTracks', count: missing, total: counts.tracks_total });
  }
  if (downloads.includes('failed') && counts.tracks_failed > 0) result.push({ key: 'failedTracks', count: counts.tracks_failed });
  if (lyrics.includes('missing') && counts.tracks_missing_lyrics > 0) {
    result.push({ key: 'missingLyrics', count: counts.tracks_missing_lyrics });
  }
  if (lyrics.includes('plain') && counts.tracks_plain_lyrics > 0) result.push({ key: 'plainLyrics', count: counts.tracks_plain_lyrics });
  if (metadata.includes('artwork') && metadataTest('artwork', item)) result.push({ key: 'noArtwork' });
  if (metadata.includes('genre') && metadataTest('genre', item)) result.push({ key: 'noGenre' });
  return result;
}

/** What the picked "needs attention" filters found in this album */
export function albumHints(album: LibraryAlbum, filters: LibraryFilters): FilterHint[] {
  return hints(album, album, filters);
}

/** The same for an artist, counted over its albums that match the filters */
export function artistHints(artist: LibraryArtist, filters: LibraryFilters, ctx: FilterContext): FilterHint[] {
  return hints(sumCounts(matchingAlbums(artist, filters, ctx)), artist, filters);
}

// ============================================================================
// SORT
// ============================================================================

export const SORT_KEYS = ['name', 'added', 'year', 'completion'] as const;
export type SortKey = typeof SORT_KEYS[number];

export interface LibrarySort {
  key: SortKey;
  order: SortOrder;
}

/** The order a key starts in when picked: the one most often wanted */
export const SORT_DEFAULT_ORDER: Record<SortKey, SortOrder> = {
  name: 'asc',
  added: 'desc',
  year: 'desc',
  completion: 'asc',
};

export const DEFAULT_SORT: LibrarySort = { key: 'name', order: 'asc' };

/** Items without a value (no year, no date) go last in either order */
function compareOptional<T>(a: T | null, b: T | null, compare: (a: T, b: T) => number, order: SortOrder): number {
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
  return order === 'asc' ? compare(a, b) : -compare(a, b);
}

const byNumber = (a: number, b: number) => a - b;
const byString = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

/** What each sort key reads from an item */
interface SortValues<T> {
  name: (item: T) => string;
  added: (item: T) => string | null;
  year: (item: T) => number | null;
  /** null when there's nothing to download: that isn't "0% done", so it goes last */
  completion: (item: T) => number | null;
}

function sortItems<T>(items: T[], sort: LibrarySort, collator: Intl.Collator, values: SortValues<T>): T[] {
  const byName = (a: T, b: T) => collator.compare(values.name(a), values.name(b));
  const compare = (a: T, b: T): number => {
    switch (sort.key) {
      case 'name':
        return sort.order === 'asc' ? byName(a, b) : -byName(a, b);
      case 'added':
        return compareOptional(values.added(a), values.added(b), byString, sort.order) || byName(a, b);
      case 'year':
        return compareOptional(values.year(a), values.year(b), byNumber, sort.order) || byName(a, b);
      case 'completion':
        return compareOptional(values.completion(a), values.completion(b), byNumber, sort.order) || byName(a, b);
    }
  };
  return [...items].sort(compare);
}

const completion = (item: { tracks_total: number; download_progress: number }) =>
  item.tracks_total > 0 ? item.download_progress : null;

export function sortAlbums(albums: LibraryAlbum[], sort: LibrarySort, collator: Intl.Collator): LibraryAlbum[] {
  return sortItems(albums, sort, collator, {
    name: (album) => album.title,
    added: (album) => album.created_at,
    year: (album) => yearOf(album.year),
    completion,
  });
}

/** An artist's newest release year among its library albums */
function latestYear(artist: LibraryArtist, ctx: FilterContext): number | null {
  let latest: number | null = null;
  for (const album of ctx.albumsByArtist.get(artist.id) ?? []) {
    const year = yearOf(album.year);
    if (year !== null && (latest === null || year > latest)) latest = year;
  }
  return latest;
}

export function sortArtists(artists: LibraryArtist[], sort: LibrarySort, ctx: FilterContext, collator: Intl.Collator): LibraryArtist[] {
  // Worked out once rather than at every comparison
  const years = sort.key === 'year' ? new Map(artists.map((artist) => [artist.id, latestYear(artist, ctx)])) : null;
  return sortItems(artists, sort, collator, {
    name: (artist) => artist.name,
    added: (artist) => artist.followed_at,
    year: (artist) => years?.get(artist.id) ?? null,
    completion,
  });
}

// ============================================================================
// URL
// ============================================================================

const SORT_PARAM = 'sort';
const ORDER_PARAM = 'order';

/** The filters of a /library URL: ?downloads=missing&genre=Rock&genre=Pop */
export function filtersFromParams(params: URLSearchParams): LibraryFilters {
  const filters: LibraryFilters = {};
  for (const group of FILTER_GROUPS) {
    const allowed = FIXED_OPTIONS[group];
    const values = [...new Set(params.getAll(group).filter((v) => v && (!allowed || allowed.includes(v))))];
    if (values.length > 0) filters[group] = values;
  }
  return filters;
}

export function sortFromParams(params: URLSearchParams): LibrarySort {
  const key = params.get(SORT_PARAM) as SortKey | null;
  if (!key || !SORT_KEYS.includes(key)) return DEFAULT_SORT;
  const order = params.get(ORDER_PARAM);
  return { key, order: order === 'asc' || order === 'desc' ? order : SORT_DEFAULT_ORDER[key] };
}

/** `params` with the filters and sort written in, defaults left out */
export function withFilterParams(params: URLSearchParams, filters: LibraryFilters, sort: LibrarySort): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const group of FILTER_GROUPS) {
    next.delete(group);
    for (const value of picked(filters, group)) next.append(group, value);
  }
  next.delete(SORT_PARAM);
  next.delete(ORDER_PARAM);
  if (sort.key !== DEFAULT_SORT.key || sort.order !== DEFAULT_SORT.order) {
    next.set(SORT_PARAM, sort.key);
    if (sort.order !== SORT_DEFAULT_ORDER[sort.key]) next.set(ORDER_PARAM, sort.order);
  }
  return next;
}
