// src/utils/memoryCache.ts

/**
 * Small in-memory caches that let a page render what it last showed right
 * away when the user comes back to it, while it refetches in the background.
 *
 * Memory only: a reload starts empty. Every cache is emptied on login and
 * logout, so one account never sees another's data.
 */

export interface MemoryCache<V> {
  get(key: string): V | undefined;
  set(key: string, value: V): void;
}

const allCaches = new Set<Map<string, unknown>>();

/** `maxEntries` - the least recently used entries are dropped past it */
export function createMemoryCache<V>(maxEntries: number): MemoryCache<V> {
  const entries = new Map<string, V>();
  allCaches.add(entries as Map<string, unknown>);

  return {
    get(key) {
      if (!entries.has(key)) return undefined;
      // Re-inserted to mark it as the most recently used
      const value = entries.get(key)!;
      entries.delete(key);
      entries.set(key, value);
      return value;
    },
    set(key, value) {
      entries.delete(key);
      entries.set(key, value);
      while (entries.size > maxEntries) {
        entries.delete(entries.keys().next().value!);
      }
    },
  };
}

export function clearMemoryCaches(): void {
  for (const entries of allCaches) entries.clear();
}
