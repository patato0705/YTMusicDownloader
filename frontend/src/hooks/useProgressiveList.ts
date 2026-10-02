// src/hooks/useProgressiveList.ts
import { useEffect, useState } from 'react';

/** How far below the viewport the sentinel triggers the next page */
const PRELOAD_MARGIN = '800px 0px';

/**
 * Renders a long list a page at a time: the first `pageSize` items, then one
 * more page each time the sentinel (placed after the list) nears the viewport.
 *
 * The whole list stays in memory, so it can still be searched and filtered
 * client-side - only the number of mounted rows is capped.
 *
 * `resetKey` - back to the first page whenever it changes (new search, other tab...)
 */
export function useProgressiveList<T>(items: T[], pageSize: number, resetKey: unknown) {
  const [count, setCount] = useState(pageSize);
  const [prevResetKey, setPrevResetKey] = useState(resetKey);
  const [sentinel, setSentinel] = useState<HTMLElement | null>(null);

  // Reset during render rather than in an effect, so a new filter never
  // mounts the previous page count first
  if (!Object.is(prevResetKey, resetKey)) {
    setPrevResetKey(resetKey);
    setCount(pageSize);
  }

  const hasMore = count < items.length;

  // Re-observed after every page: the observer only fires on changes, so a
  // sentinel still in range after a page that didn't fill the screen would
  // otherwise never load the next one
  useEffect(() => {
    if (!sentinel || !hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setCount((c) => c + pageSize);
      },
      { rootMargin: PRELOAD_MARGIN }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [sentinel, hasMore, pageSize, count]);

  return {
    visible: hasMore ? items.slice(0, count) : items,
    hasMore,
    /** Attach to an element rendered right after the list */
    sentinelRef: setSentinel,
  };
}
