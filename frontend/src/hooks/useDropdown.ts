// src/hooks/useDropdown.ts
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, RefObject } from 'react';

// Menus open right now, oldest first. A click inside a menu opened from
// another one (the language list inside the user menu) leaves the first open.
const openMenus: HTMLElement[] = [];

/** Pixels kept between a menu and the screen's edges */
const SCREEN_GUTTER = 16;
/** The least height `fitBelow` leaves a menu: below it, scrolling the page shows the rest */
const MIN_FIT_HEIGHT = 240;
/** How long a closing menu stays on screen fading out: the length of `animate-menu-out` */
const EXIT_MS = 110;

const MOTION = {
  open: 'animate-menu-in motion-reduce:animate-none',
  // Not clickable while it fades: a click goes to what is underneath
  closing: 'animate-menu-out motion-reduce:animate-none pointer-events-none',
};

const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

interface DropdownOptions {
  /**
   * An element whose left and right edges the menu stays within (e.g. the
   * page's content column), instead of the screen's. A wider menu is narrowed.
   */
  bounds?: RefObject<HTMLElement>;
  /**
   * The button is in the page, not in fixed chrome like the navbar: the menu
   * is placed in page coordinates (add `absolute` rather than `fixed`) and
   * the browser scrolls it along with the page. Nothing runs while scrolling,
   * so it never lags behind its button.
   */
  inPage?: boolean;
  /** A max height keeping the menu within the screen's bottom when it opens (it scrolls inside) */
  fitBelow?: boolean;
}

/**
 * A menu opened by a button, portaled to <body>: the navbar's blurred glass
 * would otherwise clip it and its own blur. It stays under its button through
 * scrolling and resizing, and closes on a click outside or Escape.
 *
 * It grows out of its button when it opens and fades when it closes: render
 * it while `mounted` (not `open`, which turns false as the fade starts) and
 * add `menuMotion` to its classes.
 *
 * `align`: which edge of the button the menu lines up with
 * `gap`: pixels between the button and the menu
 */
export function useDropdown(
  align: 'left' | 'right',
  gap: number,
  { bounds, inPage = false, fitBelow = false }: DropdownOptions = {},
) {
  const [open, setOpen] = useState(false);
  // Still on screen after closing, for the fade
  const [shown, setShown] = useState(false);
  const mounted = open || shown;
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Before paint: with reduced motion, a closed menu goes at once
  useLayoutEffect(() => {
    if (open) {
      setShown(true);
      return;
    }
    if (!shown) return;
    if (prefersReducedMotion()) {
      setShown(false);
      return;
    }
    const timer = window.setTimeout(() => setShown(false), EXIT_MS);
    return () => window.clearTimeout(timer);
  }, [open, shown]);

  // A fading menu is out of reach of the keyboard and screen readers. The
  // focus it held goes back to the page first, so menus that hand it back to
  // their button on closing (useMenuFocus) see it left.
  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!menu) return;
    if (!open && menu.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    menu.inert = !open;
  }, [open, mounted]);

  // Placement, from the moment the menu is on screen until it is gone
  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!mounted || !menu) return;

    const place = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) return;
      // The button went away (a navbar-only one, the window narrowed past md):
      // with nothing to anchor to or to close it from, close the menu
      if (rect.width === 0 && rect.height === 0) {
        setOpen(false);
        return;
      }
      // Without the scrollbar: `right` is measured from the inner edge
      const viewport = document.documentElement.clientWidth;
      const area = bounds?.current?.getBoundingClientRect();
      const minX = Math.max(SCREEN_GUTTER, area?.left ?? 0);
      const maxX = Math.min(viewport - SCREEN_GUTTER, area?.right ?? viewport);
      // Set on the element itself, before measuring, so the width read is
      // the one it will have (React leaves style properties it doesn't set alone)
      menu.style.maxWidth = `${maxX - minX}px`;
      const width = menu.offsetWidth;
      const top = rect.bottom + gap;
      const vertical: CSSProperties = {
        top: inPage ? top + window.scrollY : top,
        ...(fitBelow && { maxHeight: Math.max(MIN_FIT_HEIGHT, window.innerHeight - top - SCREEN_GUTTER) }),
      };
      const scrollX = inPage ? window.scrollX : 0;
      // A menu with no room on its side lines up with the button's other
      // edge instead, or failing that, with the edge of the area it overflows
      const fitsLeft = rect.left + width <= maxX;
      const fitsRight = rect.right - width >= minX;
      const left = align === 'left' ? fitsLeft : !fitsRight && fitsLeft;
      const menuLeft = left ? rect.left : fitsRight ? rect.right - width : Math.max(minX, maxX - width);
      // It grows from under the middle of its button
      const originX = Math.min(width, Math.max(0, rect.left + rect.width / 2 - menuLeft));
      const placed = { ...vertical, transformOrigin: `${originX}px top` };
      if (left || !fitsRight) {
        setMenuStyle({ ...placed, left: menuLeft + scrollX });
      } else {
        setMenuStyle({ ...placed, right: viewport - rect.right - scrollX });
      }
    };
    place();

    // A menu in the page scrolls with it on its own; one under fixed chrome
    // follows its button (the navbar moves a little as the page scrolls)
    if (!inPage) window.addEventListener('scroll', place, { passive: true });
    window.addEventListener('resize', place);
    return () => {
      window.removeEventListener('scroll', place);
      window.removeEventListener('resize', place);
    };
  }, [mounted, align, gap, bounds, inPage, fitBelow]);

  // Closing, while it is open
  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!open || !menu) return;
    openMenus.push(menu);

    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target)) return;
      if (openMenus.slice(openMenus.indexOf(menu)).some((m) => m.contains(target))) return;
      setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && openMenus[openMenus.length - 1] === menu) setOpen(false);
    };

    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
      openMenus.splice(openMenus.indexOf(menu), 1);
    };
  }, [open]);

  return {
    open,
    /** Whether to render the menu: open, or fading after closing */
    mounted,
    setOpen,
    toggle: () => setOpen((value) => !value),
    buttonRef,
    menuRef,
    /** Position of the menu (add `fixed`, or `absolute` with `inPage`) */
    menuStyle,
    /** Classes animating the menu in and out */
    menuMotion: open ? MOTION.open : MOTION.closing,
  };
}
