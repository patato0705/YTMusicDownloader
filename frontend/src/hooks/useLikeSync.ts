// src/hooks/useLikeSync.ts
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { setArtistLiked } from '../api/artists';

/** Quiet time after the last click on a heart before the server hears of it */
const LIKE_DEBOUNCE_MS = 500;

interface LikeState {
  /** What the server has, as far as we know */
  saved: boolean;
  /** What the screen shows */
  wanted: boolean;
  timer?: number;
  /** The request on its way: the next one waits for it, so they land in order */
  sending?: Promise<void>;
}

/**
 * Likes flip on screen at once, but the server only hears where a burst of
 * clicks on a heart ends up, LIKE_DEBOUNCE_MS after the last one, and
 * nothing if that's where it started. Whatever is still waiting is sent
 * when the page goes.
 *
 * `onFailed(artistId, liked)` puts a heart back to what the server has.
 * `unsaved()` gives the likes the server doesn't have yet, to lay over a
 * fresh fetch so a refresh never undoes a click.
 */
export function useLikeSync(onFailed: (artistId: string, liked: boolean) => void) {
  const states = useRef(new Map<string, LikeState>());
  const onFailedRef = useRef(onFailed);
  onFailedRef.current = onFailed;
  const mounted = useRef(true);

  const send = useCallback((artistId: string) => {
    const state = states.current.get(artistId);
    if (!state) return;
    window.clearTimeout(state.timer);
    state.timer = undefined;

    const sending = (state.sending ?? Promise.resolve()).then(async () => {
      // Read now, not when queued: a later click may have changed it
      const liked = state.wanted;
      if (liked === state.saved) return;
      try {
        await setArtistLiked(artistId, liked);
        state.saved = liked;
      } catch (err) {
        console.error('Failed to update liked artist:', err);
        window.clearTimeout(state.timer);
        state.timer = undefined;
        state.wanted = state.saved;
        if (mounted.current) onFailedRef.current(artistId, state.saved);
      }
    });
    state.sending = sending;
    sending.then(() => {
      // Settled, with nothing newer: forget it
      if (state.sending === sending && state.timer === undefined && state.wanted === state.saved) {
        states.current.delete(artistId);
      }
    });
  }, []);

  /** The heart now shows `liked` (it showed the opposite) */
  const toggle = useCallback((artistId: string, liked: boolean) => {
    let state = states.current.get(artistId);
    if (!state) {
      state = { saved: !liked, wanted: liked };
      states.current.set(artistId, state);
    }
    state.wanted = liked;
    window.clearTimeout(state.timer);
    state.timer = window.setTimeout(() => send(artistId), LIKE_DEBOUNCE_MS);
  }, [send]);

  const unsaved = useCallback((): Map<string, boolean> => {
    const likes = new Map<string, boolean>();
    for (const [artistId, state] of states.current) likes.set(artistId, state.wanted);
    return likes;
  }, []);

  useEffect(() => {
    mounted.current = true;
    const all = states.current;
    return () => {
      mounted.current = false;
      for (const [artistId, state] of all) {
        if (state.timer !== undefined) send(artistId);
      }
    };
  }, [send]);

  return useMemo(() => ({ toggle, unsaved }), [toggle, unsaved]);
}
