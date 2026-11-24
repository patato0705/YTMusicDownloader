// src/hooks/useSheetDismiss.ts
import { useCallback, useEffect, useRef } from 'react';
import type { RefObject } from 'react';

/** How long the sheet takes to slide down, and to settle back after a short swipe */
const DURATION_MS = 260;
const EASING = 'cubic-bezier(0.32, 0.72, 0, 1)';
/** Pixels a finger moves before it counts as a swipe rather than a tap */
const SLOP = 8;
/** A swipe past this share of the sheet's height closes it... */
const CLOSE_DISTANCE = 0.25;
/** ...and so does a flick faster than this, in pixels per millisecond */
const CLOSE_VELOCITY = 0.5;
/** The flick speed is the finger's over its last moments: a pause before lifting is a stop */
const VELOCITY_WINDOW_MS = 100;

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * Closing a bottom sheet: it slides back down while its backdrop fades,
 * then `onClose` runs. It can also be swiped down with a finger, from
 * anywhere on it, as long as the content under the finger is scrolled to
 * the top (mark scrolling areas with `data-sheet-scroll`).
 *
 * Returns `close`, to call instead of `onClose`. Does nothing special
 * (`close` is `onClose`) unless `enabled`.
 */
export function useSheetDismiss(
  enabled: boolean,
  panelRef: RefObject<HTMLElement>,
  backdropRef: RefObject<HTMLElement>,
  onClose: () => void,
): () => void {
  const closing = useRef(false);
  const timer = useRef<number>();
  const latest = useRef(onClose);
  latest.current = onClose;

  // A sheet unmounted mid-slide (its page left) doesn't close anything later
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const animate = (transform: string, opacity: string) => {
    const panel = panelRef.current;
    const backdrop = backdropRef.current;
    if (panel) {
      panel.style.transition = `transform ${DURATION_MS}ms ${EASING}`;
      panel.style.transform = transform;
    }
    if (backdrop) {
      backdrop.style.transition = `opacity ${DURATION_MS}ms ease`;
      backdrop.style.opacity = opacity;
    }
  };

  const close = useCallback(() => {
    if (!enabled || reducedMotion()) {
      latest.current();
      return;
    }
    if (closing.current) return;
    closing.current = true;
    animate('translateY(100%)', '0');
    timer.current = window.setTimeout(() => {
      latest.current();
      // Normally the sheet is gone now; one kept open is shown again, and closes again
      closing.current = false;
      animate('', '');
    }, DURATION_MS);
  }, [enabled]);

  useEffect(() => {
    const panel = panelRef.current;
    if (!enabled || !panel) return;

    // idle: no finger; pending: down but not moved enough to tell;
    // dragging: moving the sheet; scrolling: left to the browser
    let state: 'idle' | 'pending' | 'dragging' | 'scrolling' = 'idle';
    let startY = 0;
    let offset = 0;
    // Recent positions, for the speed the finger left with
    let samples: Array<{ y: number; t: number }> = [];
    const sample = (y: number, t: number) => {
      samples.push({ y, t });
      while (samples.length > 2 && t - samples[0].t > VELOCITY_WINDOW_MS) samples.shift();
    };

    const onStart = (event: TouchEvent) => {
      if (closing.current || event.touches.length !== 1) {
        state = 'idle';
        return;
      }
      const scroller = (event.target as HTMLElement).closest('[data-sheet-scroll]');
      state = scroller && scroller.scrollTop > 0 ? 'scrolling' : 'pending';
      startY = event.touches[0].clientY;
      offset = 0;
      samples = [{ y: startY, t: event.timeStamp }];
    };

    const onMove = (event: TouchEvent) => {
      if (state !== 'pending' && state !== 'dragging') return;
      const y = event.touches[0].clientY;
      const moved = y - startY;
      if (state === 'pending') {
        // Upwards it's a scroll of the content
        if (moved < -SLOP) state = 'scrolling';
        if (moved <= 0) return;
        // Downwards the browser mustn't start its own scroll or bounce: once
        // it has, later moves can't be held back. Cancelled from the first
        // move, before the sheet itself moves (a tap still taps). A move that
        // can't be cancelled means the browser is scrolling already: it keeps it.
        if (!event.cancelable) {
          state = 'scrolling';
          return;
        }
        event.preventDefault();
        if (moved <= SLOP) return;
        state = 'dragging';
        panel.style.transition = 'none';
        if (backdropRef.current) backdropRef.current.style.transition = 'none';
      }
      // The sheet follows the finger, not the page under it
      if (event.cancelable) event.preventDefault();
      sample(y, event.timeStamp);
      offset = Math.max(0, moved - SLOP);
      panel.style.transform = `translateY(${offset}px)`;
      if (backdropRef.current) backdropRef.current.style.opacity = String(Math.max(0, 1 - offset / panel.offsetHeight));
    };

    const onEnd = (event: TouchEvent) => {
      if (state !== 'dragging') {
        state = 'idle';
        return;
      }
      state = 'idle';
      // Moves older than the window don't count: held still, then lifted, is no flick
      const recent = samples.filter((s) => event.timeStamp - s.t <= VELOCITY_WINDOW_MS);
      const first = recent[0];
      const last = recent[recent.length - 1];
      const velocity = recent.length > 1 ? (last.y - first.y) / Math.max(1, last.t - first.t) : 0;
      if (offset > panel.offsetHeight * CLOSE_DISTANCE || velocity > CLOSE_VELOCITY) {
        close();
      } else {
        animate('', '');
      }
    };

    // The system took the touch over (a call, a gesture): settle back
    const onCancel = () => {
      if (state === 'dragging') animate('', '');
      state = 'idle';
    };

    panel.addEventListener('touchstart', onStart, { passive: true });
    panel.addEventListener('touchmove', onMove, { passive: false });
    panel.addEventListener('touchend', onEnd);
    panel.addEventListener('touchcancel', onCancel);
    return () => {
      panel.removeEventListener('touchstart', onStart);
      panel.removeEventListener('touchmove', onMove);
      panel.removeEventListener('touchend', onEnd);
      panel.removeEventListener('touchcancel', onCancel);
    };
  }, [enabled, panelRef, backdropRef, close]);

  return close;
}
