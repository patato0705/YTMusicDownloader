// src/components/ScrollRestoration.tsx
import { useEffect, useLayoutEffect, useRef } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';
import { createMemoryCache } from '../utils';

/** History entries whose scroll position is remembered */
const MAX_ENTRIES = 500;
/**
 * How long a page still loading its content is waited for before giving up on
 * getting back to where it was
 */
const RESTORE_TIMEOUT_MS = 5000;
/** Any of these means the user took over: stop pulling the page back */
const USER_SCROLL_EVENTS = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const;

const positions = createMemoryCache<number>(MAX_ENTRIES);

/**
 * Scrolls back to `y`, as soon as the page is tall enough for it: pages that
 * fetch their content on mount only reach their full height once it lands.
 * Returns a function that stops waiting.
 */
function restoreWhenReachable(y: number): () => void {
  const reachable = () => document.documentElement.scrollHeight - window.innerHeight >= y;

  window.scrollTo(0, y);
  if (reachable()) return () => {};

  const observer = new ResizeObserver(() => {
    window.scrollTo(0, y);
    if (reachable()) stop();
  });
  observer.observe(document.body);
  const timer = window.setTimeout(stop, RESTORE_TIMEOUT_MS);
  USER_SCROLL_EVENTS.forEach((type) => window.addEventListener(type, stop, { passive: true }));

  function stop() {
    observer.disconnect();
    window.clearTimeout(timer);
    USER_SCROLL_EVENTS.forEach((type) => window.removeEventListener(type, stop));
  }

  return stop;
}

/**
 * Back / forward return to where the page was scrolled; a new page opens at
 * the top. A URL replaced by the page itself (search params) keeps the
 * position. The pages keep what's needed to rebuild their content right away
 * (useHistoryState, memoryCache), the rest is waited for.
 */
export function ScrollRestoration(): null {
  const location = useLocation();
  const navigationType = useNavigationType();
  const keyRef = useRef(location.key);

  useEffect(() => {
    // The browser would restore on its own before the page is rendered
    window.history.scrollRestoration = 'manual';

    const onScroll = () => positions.set(keyRef.current, window.scrollY);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useLayoutEffect(() => {
    // First load, and StrictMode's second run of this effect
    if (keyRef.current === location.key) return;
    keyRef.current = location.key;

    if (navigationType === 'REPLACE') {
      positions.set(location.key, window.scrollY);
      return;
    }

    const saved = navigationType === 'POP' ? positions.get(location.key) : undefined;
    if (saved === undefined) {
      window.scrollTo(0, 0);
      return;
    }
    return restoreWhenReachable(saved);
  }, [location.key, navigationType]);

  return null;
}
