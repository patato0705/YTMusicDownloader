// src/hooks/usePolling.ts
import { useEffect, useRef } from 'react';

/**
 * Calls `callback` on an interval while `active` is true, and stops as soon
 * as it goes false (or the component unmounts). The callback is read from a
 * ref on every tick, so callers don't need to memoize it to avoid restarting
 * the timer on every render.
 *
 * `callback` receives an `isActive()` check -- since the callback typically
 * kicks off an async fetch, the interval firing again (or the component
 * unmounting) doesn't stop a promise already in flight, so wrap any
 * setState call after an `await`/`.then()` with `if (isActive()) ...` to
 * avoid applying a stale response.
 */
export function usePolling(
  callback: (isActive: () => boolean) => void,
  intervalMs: number,
  active: boolean
): void {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!active) return;

    const id = setInterval(() => callbackRef.current(() => mountedRef.current), intervalMs);
    return () => clearInterval(id);
  }, [active, intervalMs]);
}
