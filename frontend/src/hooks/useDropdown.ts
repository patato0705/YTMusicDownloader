// src/hooks/useDropdown.ts
import { useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';

// Menus open right now, oldest first. A click inside a menu opened from
// another one (the language list inside the user menu) leaves the first open.
const openMenus: HTMLElement[] = [];

/**
 * A menu opened by a button, portaled to <body> with fixed positioning: the
 * navbar's blurred glass would otherwise clip it and its own blur. It stays
 * under its button through scrolling and resizing, and closes on a click
 * outside or Escape.
 *
 * `align`: which edge of the button the menu lines up with
 * `gap`: pixels between the button and the menu
 */
export function useDropdown(align: 'left' | 'right', gap: number) {
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
      setMenuStyle(align === 'left'
        ? { top: rect.bottom + gap, left: rect.left }
        : { top: rect.bottom + gap, right: window.innerWidth - rect.right });
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

    window.addEventListener('scroll', place, { passive: true });
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
  }, [open, align, gap]);

  return {
    open,
    setOpen,
    toggle: () => setOpen((value) => !value),
    buttonRef,
    menuRef,
    /** Position of the menu (add `fixed`) */
    menuStyle,
  };
}
