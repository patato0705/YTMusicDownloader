// src/hooks/useHistoryState.ts
import { useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { useLocation } from 'react-router-dom';
import { createMemoryCache } from '../utils';

/** History entries remembered - older ones fall back to the initial value */
const MAX_ENTRIES = 500;

const entries = createMemoryCache<unknown>(MAX_ENTRIES);

/**
 * useState that belongs to the current history entry: leaving the page and
 * coming back to it with the back / forward buttons restores the value, while
 * opening the page anew (a link, the navbar) starts from `initial`.
 *
 * Kept in memory only, like the browser's own back / forward page state, so a
 * reload starts from `initial` too.
 *
 * `name` - unique within the page
 */
export function useHistoryState<T>(
  name: string,
  initial: T | (() => T)
): [T, Dispatch<SetStateAction<T>>] {
  const { key } = useLocation();
  const [value, setValue] = useState<T>(() => {
    const saved = entries.get(`${key}|${name}`);
    if (saved !== undefined) return saved as T;
    return typeof initial === 'function' ? (initial as () => T)() : initial;
  });

  // Also re-saved under a new key when the URL is replaced (search params),
  // which gives the same history entry a new key
  useEffect(() => {
    entries.set(`${key}|${name}`, value);
  }, [key, name, value]);

  return [value, setValue];
}
