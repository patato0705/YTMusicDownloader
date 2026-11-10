// src/hooks/useDropdown.ts
import { useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties, RefObject } from 'react';

// Menus open right now, oldest first. A click inside a menu opened from
// another one (the language list inside the user menu) leaves the first open.
const openMenus: HTMLElement[] = [];

/** Pixels kept between a menu and the screen's edges */
const SCREEN_GUTTER = 16;
/** The least height `fitBelow` leaves a menu: below it, scrolling the page shows the rest */
const MIN_FIT_HEIGHT = 240;

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
 * `align`: which edge of the button the menu lines up with
 * `gap`: pixels between the button and the menu
 */
export function useDropdown(
  align: 'left' | 'right',
  gap: number,
  { bounds, inPage = false, fitBelow = false }: DropdownOptions = {},
) {
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!open || !menu) return;

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
      if (align === 'left' ? fitsLeft : !fitsRight && fitsLeft) {
        setMenuStyle({ ...vertical, left: rect.left + scrollX });
      } else if (fitsRight) {
        setMenuStyle({ ...vertical, right: viewport - rect.right - scrollX });
      } else {
        setMenuStyle({ ...vertical, left: Math.max(minX, maxX - width) + scrollX });
      }
    };
    place();
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

    // A menu in the page scrolls with it on its own; one under fixed chrome
    // follows its button (the navbar moves a little as the page scrolls)
    if (!inPage) window.addEventListener('scroll', place, { passive: true });
    window.addEventListener('resize', place);
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('scroll', place);
      window.removeEventListener('resize', place);
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
      openMenus.splice(openMenus.indexOf(menu), 1);
    };
  }, [open, align, gap, bounds, inPage, fitBelow]);

  return {
    open,
    setOpen,
    toggle: () => setOpen((value) => !value),
    buttonRef,
    menuRef,
    /** Position of the menu (add `fixed`, or `absolute` with `inPage`) */
    menuStyle,
  };
}
