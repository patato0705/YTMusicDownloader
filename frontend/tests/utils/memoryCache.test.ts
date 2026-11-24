import { describe, expect, it } from 'vitest';
import { clearMemoryCaches, createMemoryCache } from '../../src/utils/memoryCache';

describe('createMemoryCache', () => {
  it('keeps what it is given', () => {
    const cache = createMemoryCache<number>(2);
    expect(cache.get('a')).toBeUndefined();
    cache.set('a', 1);
    cache.set('a', 2);
    expect(cache.get('a')).toBe(2);
  });

  it('drops the least recently used entry past its size', () => {
    const cache = createMemoryCache<number>(2);
    cache.set('a', 1);
    cache.set('b', 2);
    // Reading "a" makes "b" the oldest
    cache.get('a');
    cache.set('c', 3);
    expect(cache.get('a')).toBe(1);
    expect(cache.get('b')).toBeUndefined();
    expect(cache.get('c')).toBe(3);
  });
});

describe('clearMemoryCaches', () => {
  it('empties every cache, so one account never sees what another left', () => {
    const artists = createMemoryCache<string>(5);
    const albums = createMemoryCache<string>(5);
    artists.set('library', 'alice');
    albums.set('library', 'alice');
    clearMemoryCaches();
    expect(artists.get('library')).toBeUndefined();
    expect(albums.get('library')).toBeUndefined();
  });
});
