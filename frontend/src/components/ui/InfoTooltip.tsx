// src/components/ui/InfoTooltip.tsx
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface InfoTooltipProps {
  /** Tooltip body: plain text or richer markup. */
  content: React.ReactNode;
  /** Accessible name for the "i" trigger button. */
  label: string;
  className?: string;
}

const GAP = 8;     // distance between the trigger and the bubble
const MARGIN = 8;  // minimum distance from the viewport edges

/**
 * Small "i" button that reveals a bubble on hover, focus or click/tap.
 *
 * The bubble is portaled to <body> with fixed positioning so it is neither
 * clipped by overflow-hidden/auto ancestors (cards, table wrappers) nor
 * affected by their text styles (e.g. an uppercase <th>).
 */
export const InfoTooltip: React.FC<InfoTooltipProps> = ({ content, label, className = '' }) => {
  const [open, setOpen] = useState(false);
  // null until the bubble has been measured, so it is never painted at (0, 0)
  const [position, setPosition] = useState<{ top: number; left: number; arrowLeft: number; placement: 'top' | 'bottom' } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const bubbleRef = useRef<HTMLDivElement>(null);

  // Center the bubble on the trigger, above it when there is room, and keep it
  // inside the viewport horizontally (the arrow stays under the trigger).
  const updatePosition = () => {
    const button = buttonRef.current;
    const bubble = bubbleRef.current;
    if (!button || !bubble) return;

    const rect = button.getBoundingClientRect();
    const width = bubble.offsetWidth;
    const height = bubble.offsetHeight;
    const placement = rect.top - GAP - height >= MARGIN ? 'top' : 'bottom';
    const top = placement === 'top' ? rect.top - GAP - height : rect.bottom + GAP;
    const centerX = rect.left + rect.width / 2;
    const left = Math.min(Math.max(centerX - width / 2, MARGIN), window.innerWidth - width - MARGIN);

    setPosition({ top, left, arrowLeft: centerX - left, placement });
  };

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null);
      return;
    }
    updatePosition();
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);
    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [open]);

  // Click/tap outside or Escape closes a bubble opened by click (touch devices)
  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target) || bubbleRef.current?.contains(target)) return;
      setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        // Open-only: a tap fires mouseenter *then* click, so a toggle would
        // immediately close what the hover just opened. Closing is handled by
        // mouseleave/blur, tapping outside and Escape.
        onClick={() => setOpen(true)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        aria-label={label}
        aria-expanded={open}
        className={`inline-flex items-center justify-center w-4 h-4 rounded-full border border-slate-300 dark:border-white/20 text-[10px] leading-none normal-case font-serif italic text-muted-foreground hover:text-blue-600 dark:hover:text-red-400 hover:border-blue-400/50 dark:hover:border-red-600/50 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 transition-colors ${className}`}
      >
        i
      </button>

      {open && createPortal(
        <div
          ref={bubbleRef}
          role="tooltip"
          className="fixed z-50 w-72 max-w-[calc(100vw-16px)] px-4 py-3 glass rounded-xl border border-slate-200/50 dark:border-white/10 shadow-xl text-sm font-normal normal-case tracking-normal text-foreground text-left pointer-events-none transition-opacity duration-150"
          style={
            position
              ? { top: `${position.top}px`, left: `${position.left}px`, opacity: 1 }
              : { top: 0, left: 0, opacity: 0, visibility: 'hidden' }
          }
        >
          {content}
          <span
            className={`absolute border-[6px] border-transparent -translate-x-1/2 ${
              position?.placement === 'bottom'
                ? 'bottom-full border-b-slate-200/80 dark:border-b-white/10'
                : 'top-full border-t-slate-200/80 dark:border-t-white/10'
            }`}
            style={{ left: `${position?.arrowLeft ?? 0}px` }}
          />
        </div>,
        document.body,
      )}
    </>
  );
};
