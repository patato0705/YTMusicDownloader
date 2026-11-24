import { describe, expect, it } from 'vitest';
import type { LibraryAlbum, LibraryArtist } from '../../src/api/library';
import type { AlbumDownloadStatus } from '../../src/types';
import {
  albumPath,
  artistPath,
  categorizeAlbums,
  exceptionalStatus,
  formatDuration,
  formatDurationLong,
  getAlbumStatus,
  getArtistStatus,
} from '../../src/utils/mediaHelpers';

const downloading = (download_status: AlbumDownloadStatus, tracks_downloaded = 0, tracks_total = 10) =>
  ({ mode: 'download' as const, download_status, tracks_downloaded, tracks_total });

describe('getAlbumStatus', () => {
  it('shows no badge for an album that is not being downloaded', () => {
    expect(getAlbumStatus({ mode: 'metadata', download_status: 'completed' })).toBeUndefined();
    expect(getAlbumStatus({ ...downloading('completed'), in_database: false })).toBeUndefined();
  });

  it('reads the download status', () => {
    expect(getAlbumStatus(downloading('downloading'))).toBe('downloading');
    expect(getAlbumStatus(downloading('failed'))).toBe('failed');
    expect(getAlbumStatus(downloading('completed'))).toBe('downloaded');
    expect(getAlbumStatus(downloading('idle'))).toBe('in_library');
    expect(getAlbumStatus(downloading(null))).toBe('in_library');
  });

  it('keeps the spinner between two tracks of an album already started', () => {
    expect(getAlbumStatus(downloading('pending', 0))).toBe('queued');
    expect(getAlbumStatus(downloading('pending', 4))).toBe('downloading');
    expect(getAlbumStatus(downloading('pending', 10))).toBe('queued');
    // The artist page has no track counts
    expect(getAlbumStatus({ mode: 'download', download_status: 'pending' })).toBe('queued');
  });

  it('shows downloads still to come as paused while downloads are paused', () => {
    expect(getAlbumStatus(downloading('downloading'), true)).toBe('paused');
    expect(getAlbumStatus(downloading('pending'), true)).toBe('paused');
    expect(getAlbumStatus(downloading('completed'), true)).toBe('downloaded');
    expect(getAlbumStatus(downloading('failed'), true)).toBe('failed');
  });
});

describe('getArtistStatus', () => {
  const artist = (overrides: Partial<LibraryArtist> = {}) =>
    ({ tracks_total: 10, tracks_downloaded: 10, tracks_failed: 0, ...overrides } as LibraryArtist);
  const album = (download_status: AlbumDownloadStatus) => downloading(download_status) as LibraryAlbum;

  it('shows the most pressing state among its albums', () => {
    expect(getArtistStatus(artist(), [album('failed'), album('pending'), album('downloading')])).toBe('downloading');
    expect(getArtistStatus(artist(), [album('failed'), album('pending')], true)).toBe('paused');
    expect(getArtistStatus(artist(), [album('failed'), album('pending')])).toBe('queued');
    expect(getArtistStatus(artist(), [album('completed'), album('failed')])).toBe('failed');
  });

  it('falls back on its track counts', () => {
    expect(getArtistStatus(artist())).toBe('downloaded');
    expect(getArtistStatus(artist({ tracks_failed: 1 }))).toBe('failed');
    expect(getArtistStatus(artist({ tracks_downloaded: 3 }))).toBe('in_library');
    // Nothing to download isn't "downloaded"
    expect(getArtistStatus(artist({ tracks_total: 0, tracks_downloaded: 0 }))).toBe('in_library');
  });
});

describe('categorizeAlbums', () => {
  it('puts singles and EPs apart, and anything else with the albums', () => {
    const releases = [{ type: 'Album' }, { type: 'Single' }, { type: 'EP' }, { type: 'Compilation' }];
    expect(categorizeAlbums(releases)).toEqual({
      albums: [{ type: 'Album' }, { type: 'Compilation' }],
      singles: [{ type: 'Single' }, { type: 'EP' }],
    });
  });
});

describe('durations', () => {
  it('formats a track length as M:SS', () => {
    expect(formatDuration(0)).toBe('--:--');
    expect(formatDuration(null)).toBe('--:--');
    expect(formatDuration(-1)).toBe('--:--');
    expect(formatDuration(5)).toBe('0:05');
    expect(formatDuration(185.9)).toBe('3:05');
    expect(formatDuration(3600)).toBe('60:00');
  });

  it('formats a total length in hours and minutes', () => {
    expect(formatDurationLong(undefined)).toBe('0 min');
    expect(formatDurationLong(59)).toBe('0 min');
    expect(formatDurationLong(42 * 60)).toBe('42 min');
    expect(formatDurationLong(3 * 3600 + 24 * 60 + 30)).toBe('3h 24m');
  });
});

describe('paths', () => {
  it('escapes IDs in page links', () => {
    expect(artistPath('UC_abc')).toBe('/artists/UC_abc');
    expect(albumPath('MPREb/../x?y')).toBe('/albums/MPREb%2F..%2Fx%3Fy');
  });
});

describe('exceptionalStatus', () => {
  it('only badges what is not downloaded', () => {
    expect(exceptionalStatus('downloaded')).toBeUndefined();
    expect(exceptionalStatus('failed')).toBe('failed');
  });
});
