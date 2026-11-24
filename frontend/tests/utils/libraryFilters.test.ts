import { describe, expect, it } from 'vitest';
import type { LibraryAlbum, LibraryArtist } from '../../src/api/library';
import type { MediaStatus } from '../../src/types';
import {
  activeFilterCount,
  albumHints,
  albumMatches,
  artistHints,
  artistMatches,
  decadeOf,
  DEFAULT_SORT,
  filterCounts,
  filtersFromParams,
  libraryOptionCounts,
  releaseKind,
  showsExcluded,
  sortAlbums,
  sortArtists,
  sortFromParams,
  toggleFilter,
  UNKNOWN_DECADE,
  withFilterParams,
  type FilterContext,
  type FilterGroup,
  type LibraryFilters,
} from '../../src/utils/libraryFilters';

const collator = new Intl.Collator('en');

function artist(id: string, overrides: Partial<LibraryArtist> = {}): LibraryArtist {
  return {
    id,
    name: id,
    thumbnail: 'thumb.jpg',
    genres: [],
    genres_checked: false,
    mode: 'full',
    chart_followed: false,
    liked: false,
    followed_at: null,
    albums_count: 0,
    tracks_total: 0,
    tracks_downloaded: 0,
    tracks_failed: 0,
    download_progress: 0,
    last_synced_at: null,
    ...overrides,
  };
}

/** A complete 10-track album by `artistId`, with synced lyrics throughout */
function album(id: string, artistId: string | null, overrides: Partial<LibraryAlbum> = {}): LibraryAlbum {
  return {
    id,
    title: id,
    removed_at: null,
    artist: artistId ? { id: artistId, name: artistId } : null,
    year: '2020',
    type: 'Album',
    mode: 'download',
    thumbnail: 'thumb.jpg',
    download_status: 'completed',
    tracks_total: 10,
    tracks_downloaded: 10,
    tracks_failed: 0,
    tracks_missing_lyrics: 0,
    tracks_synced_lyrics: 10,
    tracks_plain_lyrics: 0,
    tracks_instrumental: 0,
    genres: [],
    genres_checked: false,
    from_playlist: false,
    download_progress: 100,
    created_at: null,
    ...overrides,
  };
}

function context(artists: LibraryArtist[], albums: LibraryAlbum[], status: Record<string, MediaStatus> = {}): FilterContext {
  const albumsByArtist = new Map<string, LibraryAlbum[]>();
  for (const a of albums) {
    if (!a.artist) continue;
    albumsByArtist.set(a.artist.id, [...(albumsByArtist.get(a.artist.id) ?? []), a]);
  }
  return {
    artistById: new Map(artists.map((a) => [a.id, a])),
    albumsByArtist,
    albumStatus: new Map(Object.entries(status)),
  };
}

const ids = (items: { id: string }[]) => items.map((item) => item.id);

describe('releaseKind', () => {
  it('reads singles and EPs whatever the case, and lists anything else as an album', () => {
    expect(releaseKind('Single')).toBe('single');
    expect(releaseKind(' EP ')).toBe('ep');
    expect(releaseKind('Album')).toBe('album');
    expect(releaseKind('Compilation')).toBe('album');
    expect(releaseKind(null)).toBe('album');
  });
});

describe('decadeOf', () => {
  it('rounds a year down to its decade', () => {
    expect(decadeOf('1994')).toBe('1990');
    expect(decadeOf('2000')).toBe('2000');
  });

  it('gives UNKNOWN_DECADE when there is no usable year', () => {
    expect(decadeOf(null)).toBe(UNKNOWN_DECADE);
    expect(decadeOf('')).toBe(UNKNOWN_DECADE);
    expect(decadeOf('0')).toBe(UNKNOWN_DECADE);
    expect(decadeOf('unknown')).toBe(UNKNOWN_DECADE);
  });
});

describe('albumMatches', () => {
  const singer = artist('singer');
  const complete = album('complete', 'singer');
  const missing = album('missing', 'singer', { tracks_downloaded: 6 });
  const failed = album('failed', 'singer', { tracks_downloaded: 9, tracks_failed: 1 });
  const ctx = context([singer], [complete, missing, failed]);
  const matching = (filters: LibraryFilters) => ids([complete, missing, failed].filter((a) => albumMatches(a, filters, ctx)));

  it('lets everything through without filters', () => {
    expect(matching({})).toEqual(['complete', 'missing', 'failed']);
    expect(matching({ downloads: [] })).toEqual(['complete', 'missing', 'failed']);
  });

  it('matches any value picked within a group', () => {
    expect(matching({ downloads: ['missing'] })).toEqual(['missing', 'failed']);
    expect(matching({ downloads: ['failed'] })).toEqual(['failed']);
    expect(matching({ downloads: ['missing', 'failed'] })).toEqual(['missing', 'failed']);
  });

  it('needs every group picked to match', () => {
    const single = album('single', 'singer', { type: 'Single', tracks_downloaded: 0 });
    const both = context([singer], [single, missing]);
    expect([single, missing].filter((a) => albumMatches(a, { downloads: ['missing'], type: ['single'] }, both))).toEqual([single]);
  });

  it('counts a queued, running or paused download as active, from the status map', () => {
    const active = context([singer], [complete, missing], { missing: 'queued' });
    expect(albumMatches(missing, { downloads: ['active'] }, active)).toBe(true);
    expect(albumMatches(complete, { downloads: ['active'] }, active)).toBe(false);
    expect(albumMatches(complete, { downloads: ['failed'] }, context([singer], [complete], { complete: 'failed' }))).toBe(true);
  });

  it('tells apart albums followed with their artist, from a playlist, and added on their own', () => {
    const light = artist('light', { mode: 'light' });
    const byArtist = album('by-artist', 'singer');
    const fromPlaylist = album('from-playlist', 'light', { from_playlist: true });
    const own = album('own', 'light');
    const orphan = album('orphan', null);
    const albums = [byArtist, fromPlaylist, own, orphan];
    const ctx2 = context([singer, light], albums);
    const bySource = (value: string) => ids(albums.filter((a) => albumMatches(a, { source: [value] }, ctx2)));
    expect(bySource('artist')).toEqual(['by-artist']);
    expect(bySource('playlist')).toEqual(['from-playlist']);
    expect(bySource('own')).toEqual(['own', 'orphan']);
  });

  it('tests artist groups through the album artist, and fails them without one', () => {
    const liked = artist('liked', { liked: true });
    const likedAlbum = album('liked-album', 'liked');
    const orphan = album('orphan', null);
    const ctx2 = context([singer, liked], [complete, likedAlbum, orphan]);
    expect(ids([complete, likedAlbum, orphan].filter((a) => albumMatches(a, { liked: ['liked'] }, ctx2)))).toEqual(['liked-album']);
  });

  it('only flags a missing genre once genres were looked up', () => {
    const unchecked = album('unchecked', 'singer');
    const none = album('none', 'singer', { genres_checked: true });
    const rock = album('rock', 'singer', { genres_checked: true, genres: ['Rock'] });
    const ctx2 = context([singer], [unchecked, none, rock]);
    expect(ids([unchecked, none, rock].filter((a) => albumMatches(a, { metadata: ['genre'] }, ctx2)))).toEqual(['none']);
  });
});

describe('artistMatches', () => {
  it('needs one album matching every album group at once', () => {
    // "singles missing lyrics" means one single missing lyrics, not a single
    // and some other album missing lyrics
    const singer = artist('singer');
    const singleWithLyrics = album('single', 'singer', { type: 'Single' });
    const albumMissingLyrics = album('album', 'singer', { tracks_missing_lyrics: 3 });
    const filters: LibraryFilters = { type: ['single'], lyrics: ['missing'] };
    expect(artistMatches(singer, filters, context([singer], [singleWithLyrics, albumMissingLyrics]))).toBe(false);

    const singleMissingLyrics = album('single-2', 'singer', { type: 'Single', tracks_missing_lyrics: 1 });
    const albums = [singleWithLyrics, albumMissingLyrics, singleMissingLyrics];
    expect(artistMatches(singer, filters, context([singer], albums))).toBe(true);
  });

  it('applies artist and metadata groups to the artist itself', () => {
    const liked = artist('liked', { liked: true, thumbnail: null });
    const plain = artist('plain');
    const ctx = context([liked, plain], []);
    expect(artistMatches(liked, { liked: ['liked'] }, ctx)).toBe(true);
    expect(artistMatches(plain, { liked: ['liked'] }, ctx)).toBe(false);
    expect(artistMatches(liked, { metadata: ['artwork'] }, ctx)).toBe(true);
    expect(artistMatches(plain, { metadata: ['artwork'] }, ctx)).toBe(false);
  });

  it('reads the follow mode, and chart follows apart from it', () => {
    const full = artist('full');
    const light = artist('light', { mode: 'light' });
    const chart = artist('chart', { mode: 'light', chart_followed: true });
    const ctx = context([full, light, chart], []);
    const byFollow = (value: string) => ids([full, light, chart].filter((a) => artistMatches(a, { follow: [value] }, ctx)));
    expect(byFollow('full')).toEqual(['full']);
    expect(byFollow('light')).toEqual(['light', 'chart']);
    expect(byFollow('chart')).toEqual(['chart']);
  });

  it('leaves out an artist without albums once an album group is picked', () => {
    const empty = artist('empty');
    expect(artistMatches(empty, { type: ['album'] }, context([empty], []))).toBe(false);
  });
});

describe('toggleFilter', () => {
  it('picks and unpicks a value, dropping a group left empty', () => {
    let filters = toggleFilter({}, 'genre', 'Rock');
    expect(filters).toEqual({ genre: ['Rock'] });
    filters = toggleFilter(filters, 'genre', 'Pop');
    expect(filters).toEqual({ genre: ['Rock', 'Pop'] });
    filters = toggleFilter(filters, 'genre', 'Rock');
    expect(filters).toEqual({ genre: ['Pop'] });
    expect(toggleFilter(filters, 'genre', 'Pop')).toEqual({});
  });

  it('never changes the filters it was given', () => {
    const filters: LibraryFilters = { genre: ['Rock'] };
    toggleFilter(filters, 'genre', 'Pop');
    expect(filters).toEqual({ genre: ['Rock'] });
  });

  it('keeps "excluded" apart from every other filter', () => {
    const excluded = toggleFilter({ genre: ['Rock'], liked: ['liked'] }, 'excluded', 'excluded');
    expect(excluded).toEqual({ excluded: ['excluded'] });
    expect(showsExcluded(excluded)).toBe(true);
    expect(toggleFilter(excluded, 'type', 'single')).toEqual({ type: ['single'] });
    expect(toggleFilter(excluded, 'excluded', 'excluded')).toEqual({});
  });
});

describe('activeFilterCount', () => {
  it('counts every picked value', () => {
    expect(activeFilterCount({})).toBe(0);
    expect(activeFilterCount({ genre: ['Rock', 'Pop'], liked: ['liked'], type: [] })).toBe(3);
  });
});

describe('option counts', () => {
  const singer = artist('singer');
  const band = artist('band', { liked: true });
  const albums = [
    album('a', 'singer', { genres: ['Rock'], year: '1994' }),
    album('b', 'singer', { genres: ['Rock', 'Pop'], year: '2003', tracks_downloaded: 2 }),
    album('c', 'band', { genres: ['Pop'], year: '2005' }),
    album('d', 'band', { genres: ['Jazz'], year: null }),
  ];
  const library = { artists: [singer, band], albums };
  const ctx = context([singer, band], albums);
  const groups: FilterGroup[] = ['genre', 'decade', 'downloads', 'metadata', 'excluded'];
  const counts = libraryOptionCounts(library, ctx, { groups, genresLookedUp: false, excludedCount: 2 }, collator);

  it('lists genres by how many albums have them, then by name', () => {
    expect([...counts.get('genre')!.keys()]).toEqual(['Pop', 'Rock', 'Jazz']);
  });

  it('lists decades newest first, albums without a year last', () => {
    expect([...counts.get('decade')!.keys()]).toEqual(['2000', '1990', UNKNOWN_DECADE]);
  });

  it('counts the albums and artists each option finds', () => {
    // Rock: albums a and b, plus their artist
    expect(counts.get('genre')!.get('Rock')).toBe(3);
    // 2000s: albums b and c, plus both artists
    expect(counts.get('decade')!.get('2000')).toBe(4);
    expect(counts.get('downloads')!.get('missing')).toBe(2);
    expect(counts.get('excluded')!.get('excluded')).toBe(2);
  });

  it('only offers "no genre found" once genres are looked up', () => {
    expect([...counts.get('metadata')!.keys()]).toEqual(['artwork']);
    const lookedUp = libraryOptionCounts(library, ctx, { groups, genresLookedUp: true, excludedCount: 0 }, collator);
    expect([...lookedUp.get('metadata')!.keys()]).toEqual(['artwork', 'genre']);
  });

  it("counts each option with the other groups applied, but not its own group's", () => {
    const filters: LibraryFilters = { genre: ['Rock'], liked: ['liked'] };
    const shown = filterCounts(library, counts, filters, ctx);
    const genre = shown.find((g) => g.group === 'genre')!.options;
    // Only the liked band's albums count: Pop finds album c and the band, Rock
    // nothing. In the whole library, Pop is on albums b and c, and both artists
    expect(genre.find((o) => o.value === 'Pop')).toEqual({ value: 'Pop', count: 2, libraryCount: 4 });
    expect(genre.find((o) => o.value === 'Rock')).toEqual({ value: 'Rock', count: 0, libraryCount: 3 });
  });

  it('keeps a picked value the library no longer has, so it can be unpicked', () => {
    const shown = filterCounts(library, counts, { genre: ['Metal'] }, ctx);
    const genre = shown.find((g) => g.group === 'genre')!.options;
    expect(genre[genre.length - 1]).toEqual({ value: 'Metal', count: 0, libraryCount: 0 });
  });
});

describe('hints', () => {
  it("says what the picked filters found in an album", () => {
    const partial = album('partial', 'singer', { tracks_downloaded: 7, tracks_failed: 1, tracks_missing_lyrics: 2, thumbnail: null });
    expect(albumHints(partial, {})).toEqual([]);
    expect(albumHints(partial, { downloads: ['missing', 'failed'], lyrics: ['missing'], metadata: ['artwork'] })).toEqual([
      { key: 'missingTracks', count: 3, total: 10 },
      { key: 'failedTracks', count: 1 },
      { key: 'missingLyrics', count: 2 },
      { key: 'noArtwork' },
    ]);
  });

  it("adds up an artist's albums that match the filters", () => {
    const singer = artist('singer');
    const albums = [
      album('a', 'singer', { type: 'Single', tracks_total: 2, tracks_downloaded: 1 }),
      album('b', 'singer', { type: 'Single', tracks_total: 3, tracks_downloaded: 1 }),
      album('c', 'singer', { tracks_downloaded: 0 }),
    ];
    const ctx = context([singer], albums);
    expect(artistHints(singer, { downloads: ['missing'], type: ['single'] }, ctx)).toEqual([
      { key: 'missingTracks', count: 3, total: 5 },
    ]);
  });
});

describe('sort', () => {
  it('sorts by name with the collator, either way', () => {
    const albums = [album('b', null), album('a', null), album('C', null)];
    expect(ids(sortAlbums(albums, { key: 'name', order: 'asc' }, collator))).toEqual(['a', 'b', 'C']);
    expect(ids(sortAlbums(albums, { key: 'name', order: 'desc' }, collator))).toEqual(['C', 'b', 'a']);
  });

  it('puts items without a value last in either order, then sorts them by name', () => {
    const albums = [
      album('no-date-b', null),
      album('old', null, { created_at: '2024-01-01T00:00:00Z' }),
      album('no-date-a', null),
      album('new', null, { created_at: '2025-06-01T00:00:00Z' }),
    ];
    expect(ids(sortAlbums(albums, { key: 'added', order: 'desc' }, collator))).toEqual(['new', 'old', 'no-date-a', 'no-date-b']);
    expect(ids(sortAlbums(albums, { key: 'added', order: 'asc' }, collator))).toEqual(['old', 'new', 'no-date-a', 'no-date-b']);
  });

  it('puts albums with nothing to download after 0% done', () => {
    const albums = [
      album('empty', null, { tracks_total: 0, download_progress: 0 }),
      album('done', null, { download_progress: 100 }),
      album('started', null, { download_progress: 0 }),
    ];
    expect(ids(sortAlbums(albums, { key: 'completion', order: 'asc' }, collator))).toEqual(['started', 'done', 'empty']);
  });

  it("sorts artists by their newest album's year", () => {
    const old = artist('old');
    const recent = artist('recent');
    const none = artist('none');
    const ctx = context([old, recent, none], [
      album('a', 'old', { year: '1990' }),
      album('b', 'recent', { year: '1985' }),
      album('c', 'recent', { year: '2021' }),
      album('d', 'none', { year: null }),
    ]);
    expect(ids(sortArtists([old, none, recent], { key: 'year', order: 'desc' }, ctx, collator))).toEqual(['recent', 'old', 'none']);
  });

  it('never changes the list it was given', () => {
    const albums = [album('b', null), album('a', null)];
    sortAlbums(albums, DEFAULT_SORT, collator);
    expect(ids(albums)).toEqual(['b', 'a']);
  });
});

describe('URL', () => {
  it('reads filters, dropping values a fixed group does not have and repeats', () => {
    const params = new URLSearchParams('downloads=missing&downloads=bogus&genre=Rock&genre=Rock&genre=Hip-Hop&liked=');
    expect(filtersFromParams(params)).toEqual({ downloads: ['missing'], genre: ['Rock', 'Hip-Hop'] });
  });

  it('reads the sort, falling back to the defaults', () => {
    expect(sortFromParams(new URLSearchParams())).toEqual(DEFAULT_SORT);
    expect(sortFromParams(new URLSearchParams('sort=bogus'))).toEqual(DEFAULT_SORT);
    // Each key starts in the order most often wanted
    expect(sortFromParams(new URLSearchParams('sort=added'))).toEqual({ key: 'added', order: 'desc' });
    expect(sortFromParams(new URLSearchParams('sort=added&order=asc'))).toEqual({ key: 'added', order: 'asc' });
    expect(sortFromParams(new URLSearchParams('sort=added&order=sideways'))).toEqual({ key: 'added', order: 'desc' });
  });

  it('writes filters and sort, leaving defaults out and other params alone', () => {
    const params = new URLSearchParams('tab=albums&genre=Old');
    expect(withFilterParams(params, {}, DEFAULT_SORT).toString()).toBe('tab=albums');
    expect(withFilterParams(params, { genre: ['Rock', 'Pop'] }, { key: 'added', order: 'desc' }).toString())
      .toBe('tab=albums&genre=Rock&genre=Pop&sort=added');
    expect(withFilterParams(params, {}, { key: 'added', order: 'asc' }).toString()).toBe('tab=albums&sort=added&order=asc');
  });

  it('reads back what it writes', () => {
    const filters: LibraryFilters = { downloads: ['missing', 'failed'], genre: ['R&B', 'Drum & Bass'], liked: ['liked'] };
    const sort = { key: 'year', order: 'asc' } as const;
    const params = withFilterParams(new URLSearchParams(), filters, sort);
    expect(filtersFromParams(params)).toEqual(filters);
    expect(sortFromParams(params)).toEqual(sort);
  });
});
