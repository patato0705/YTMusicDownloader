// src/components/ui/Modal.tsx
import React, { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../contexts/I18nContext';
import { useSheetDismiss } from '../../hooks/useSheetDismiss';
import { Icon } from './icons';

interface ModalProps {
  onClose: () => void;
  /**
   * Escape and clicks outside close it. Turn off while closing would lose
   * something: a request running, unsaved text, a password shown only once.
   */
  dismissible?: boolean;
  /** Heading with a close button. Dialogs drawing their own header leave it out and pass labelledBy. */
  title?: React.ReactNode;
  /** Line under the title */
  subtitle?: React.ReactNode;
  /** Shown before the close button (e.g. a badge) */
  headerExtra?: React.ReactNode;
  labelledBy?: string;
  size?: 'md' | 'lg' | 'xl';
  /**
   * A bottom sheet instead of a centered dialog (phones): full width, slides
   * up from the bottom edge, at most 85% of the screen tall, and back down
   * when closed or swiped down (see useSheetDismiss). The page under it
   * stops scrolling while it is open.
   */
  sheet?: boolean;
  /** Extra classes on the panel (e.g. a flex column) */
  className?: string;
  /** A function gets `close`, which closes the way Escape does (a sheet slides down first) */
  children: React.ReactNode | ((close: () => void) => React.ReactNode);
}

const WIDTHS = { md: 'max-w-md', lg: 'max-w-lg', xl: 'max-w-2xl' };

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Open modals, oldest first: only the top one answers Escape and keeps focus
const openModals: HTMLElement[] = [];

/**
 * A dialog over the page: rendered into <body>, keeps keyboard focus inside
 * while open and gives it back to what had it when closed.
 */
export const Modal: React.FC<ModalProps> = ({
  onClose,
  dismissible = true,
  title,
  subtitle,
  headerExtra,
  labelledBy,
  size = 'md',
  sheet = false,
  className = '',
  children,
}) => {
  const { t } = useI18n();
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  // A click only closes when it started on the backdrop too: selecting text
  // in the dialog and releasing outside of it mustn't
  const pressedBackdrop = useRef(false);
  const close = useSheetDismiss(sheet && dismissible, panelRef, backdropRef, onClose);
  // Read by the listeners below, which are only set up once
  const latest = useRef({ close, dismissible });
  latest.current = { close, dismissible };

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    openModals.push(panel);
    if (!panel.contains(document.activeElement)) panel.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (openModals[openModals.length - 1] !== panel) return;
      // An Escape already taken (an open bubble inside) closes only that
      if (event.key === 'Escape' && latest.current.dismissible && !event.defaultPrevented) {
        event.preventDefault();
        latest.current.close();
      } else if (event.key === 'Tab') {
        // Wrap around instead of leaving for the page underneath
        const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
        if (focusable.length === 0) {
          event.preventDefault();
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKeyDown);

    // A sheet covers the bottom of the page, which could otherwise be
    // scrolled behind it by a swipe that starts on the backdrop
    const overflow = document.body.style.overflow;
    if (sheet) document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener('keydown', onKeyDown);
      openModals.splice(openModals.indexOf(panel), 1);
      previouslyFocused?.focus?.();
    };
  }, []);

  return createPortal(
    <div
      className={`fixed inset-0 z-50 flex justify-center ${sheet ? 'items-end' : 'items-center p-4 bg-black/60'}`}
      onMouseDown={(e) => { pressedBackdrop.current = e.target === e.currentTarget || e.target === backdropRef.current; }}
      onClick={(e) => {
        const onBackdrop = e.target === e.currentTarget || e.target === backdropRef.current;
        if (onBackdrop && pressedBackdrop.current && dismissible) close();
      }}
    >
      {/* A sheet's backdrop is a layer of its own, so it can fade without the sheet */}
      {sheet && (
        <div ref={backdropRef} className="absolute inset-0 bg-black/60 animate-fade-in motion-reduce:animate-none" />
      )}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : labelledBy}
        tabIndex={-1}
        className={`relative w-full shadow-2xl outline-none ${
          sheet
            ? 'glass-chrome !border-x-0 !border-b-0 rounded-t-3xl max-h-[85dvh] overflow-hidden flex flex-col animate-sheet-up motion-reduce:animate-none'
            : `glass rounded-3xl p-6 sm:p-8 ${WIDTHS[size]} max-h-[calc(100dvh-2rem)] overflow-y-auto border-gradient`
        } ${className}`}
      >
        {title && (
          <div className="flex items-start justify-between gap-4 mb-6 shrink-0">
            <div className="min-w-0">
              <h2 id={titleId} className="text-2xl font-bold text-foreground truncate">{title}</h2>
              {subtitle && <div className="text-sm text-muted-foreground truncate mt-1">{subtitle}</div>}
            </div>
            <div className="flex items-center gap-3 shrink-0">
              {headerExtra}
              <button
                type="button"
                onClick={close}
                disabled={!dismissible}
                aria-label={t('common.close')}
                className="w-8 h-8 flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/10 disabled:opacity-50 transition-all text-sm"
              >
                <Icon name="close" className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
        {typeof children === 'function' ? children(close) : children}
      </div>
    </div>,
    document.body,
  );
};
