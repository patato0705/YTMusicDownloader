// src/components/onboarding/OnboardingDialog.tsx
/**
 * The welcome tour: opens at an account's first sign-in (once the app is
 * usable, so not over a temporary password), with slides for its role.
 * However it's closed, it's done for good: the server remembers it for the
 * account, so it doesn't open again on another device or after a role change.
 */
import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { Role } from '../../api/auth';
import type { Features } from '../../api/features';
import { useAuth } from '../../contexts/AuthContext';
import { useFeatures } from '../../contexts/FeaturesContext';
import { useI18n } from '../../contexts/I18nContext';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { Button, buttonClass } from '../ui/Button';
import { Icon } from '../ui/icons';
import { Modal } from '../ui/Modal';
import { slidesFor } from './slides';

/** Pixels a finger moves sideways for a swipe to change slides */
const SWIPE_DISTANCE = 50;

export const OnboardingDialog: React.FC = () => {
  const { user, hasFullAccess, markOnboardingSeen } = useAuth();
  const { features } = useFeatures();
  // Waits for the feature flags, which decide some of the slides
  if (!user || !hasFullAccess || user.onboarding_seen || !features) return null;
  return <Tour role={user.role} name={user.username} features={features} onClose={markOnboardingSeen} />;
};

interface TourProps {
  role: Role;
  name: string;
  features: Features;
  onClose: () => void;
}

const Tour: React.FC<TourProps> = ({ role, name, features, onClose }) => {
  const { t } = useI18n();
  const wide = useMediaQuery('(min-width: 768px)');
  const labelId = useId();
  const slides = useMemo(() => slidesFor(role, features), [role, features]);
  const [index, setIndex] = useState(0);
  const total = slides.length;
  const last = index === total - 1;
  const go = (next: number) => setIndex(Math.max(0, Math.min(total - 1, next)));

  // Arrow keys move between slides (unless something in the slide used them)
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      // Not the browser's: it would scroll the dialog sideways
      event.preventDefault();
      setIndex((i) => (event.key === 'ArrowRight' ? Math.min(total - 1, i + 1) : Math.max(0, i - 1)));
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [total]);

  // A slide change can take the focused button away (Back on the first
  // slide, a hidden slide's control): the focus goes to Next then, rather
  // than to the page under the dialog
  const contentRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const focused = document.activeElement;
    if (!focused || !contentRef.current?.contains(focused) || focused.closest('[aria-hidden="true"]')) {
      nextRef.current?.focus();
    }
  }, [index]);

  // Sideways swipes on phones
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const onTouchStart = (event: React.TouchEvent) => {
    const touch = event.touches[0];
    touchStart.current = event.touches.length === 1 ? { x: touch.clientX, y: touch.clientY } : null;
  };
  const onTouchEnd = (event: React.TouchEvent) => {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) > SWIPE_DISTANCE && Math.abs(dx) > 1.5 * Math.abs(dy)) go(index + (dx < 0 ? 1 : -1));
  };

  const header = (close: () => void) => (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-baseline gap-2 text-xs font-semibold uppercase tracking-wider">
        <span id={labelId} className="text-accent-600 dark:text-accent-400">{t('onboarding.label')}</span>
        <span className="text-muted-foreground tabular-nums">{t('onboarding.step', { current: index + 1, total })}</span>
      </div>
      <button
        type="button"
        onClick={close}
        aria-label={t('common.close')}
        className="w-10 h-10 -mr-2 flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/10 transition-colors"
      >
        <Icon name="close" />
      </button>
    </div>
  );

  // Every slide in the same grid cell, the others hidden: the dialog keeps
  // the height of the tallest instead of jumping from one slide to the next
  const content = (close: () => void) => (
    <div className="grid" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
      {slides.map((slide, i) => {
        const Visual = slide.visual;
        const active = i === index;
        return (
          <section
            key={slide.id}
            aria-hidden={!active}
            // Hidden at once: visibility is inherited and animatable, so a
            // control with transition-all inside would stay up for its duration
            className={`[grid-area:1/1] min-w-0 ${active ? 'animate-fade-in motion-reduce:animate-none' : 'invisible [&_*]:!transition-none'}`}
          >
            {!slide.controls && <Visual role={role} close={close} />}
            <h2 className="text-xl sm:text-2xl font-bold text-foreground">{t(slide.title, { name })}</h2>
            <p className="mt-2 text-sm sm:text-base text-muted-foreground leading-relaxed">{t(slide.body(role))}</p>
            {slide.controls && <Visual role={role} close={close} />}
          </section>
        );
      })}
      {/* Hidden slides aren't read: this says which one came up */}
      <p className="sr-only" aria-live="polite">{t(slides[index].title, { name })}</p>
    </div>
  );

  const footer = (close: () => void) => (
    <div className="space-y-3">
      <div className="flex items-center justify-center">
        {slides.map((slide, i) => (
          <button
            key={slide.id}
            type="button"
            onClick={() => go(i)}
            aria-label={t('onboarding.goTo', { current: i + 1, total })}
            aria-current={i === index ? 'step' : undefined}
            className="p-1.5 group rounded-full outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
          >
            <span
              className={`block h-2 rounded-full transition-all duration-300 ${
                i === index
                  ? 'w-6 bg-accent-600 dark:bg-accent-400'
                  : 'w-2 bg-slate-300 dark:bg-white/20 group-hover:bg-slate-400 dark:group-hover:bg-white/40'
              }`}
            />
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        {!last && <Button variant="ghost" onClick={close}>{t('onboarding.skip')}</Button>}
        <span className="flex-1" />
        {index > 0 && <Button variant="secondary" onClick={() => go(index - 1)}>{t('common.back')}</Button>}
        <button ref={nextRef} type="button" className={buttonClass('primary')} onClick={() => (last ? close() : go(index + 1))}>
          {last ? t('onboarding.finish') : t('onboarding.next')}
        </button>
      </div>
    </div>
  );

  // The dialog and the sheet are different panels: crossing the breakpoint
  // (a tablet turned) swaps one for the other, on the same slide
  return wide ? (
    <Modal key="dialog" size="lg" labelledBy={labelId} onClose={onClose}>
      {(close) => (
        <div ref={contentRef}>
          <div className="mb-4">{header(close)}</div>
          {content(close)}
          <div className="mt-6">{footer(close)}</div>
        </div>
      )}
    </Modal>
  ) : (
    <Modal key="sheet" sheet labelledBy={labelId} onClose={onClose}>
      {(close) => (
        <div ref={contentRef} className="flex-1 min-h-0 flex flex-col">
          <div className="shrink-0 px-5">
            {/* Says the sheet can be swiped down (useSheetDismiss) */}
            <div className="mx-auto mt-2.5 mb-1 h-1.5 w-10 rounded-full bg-slate-300 dark:bg-white/20" aria-hidden="true" />
            {header(close)}
          </div>
          <div data-sheet-scroll className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-5 pt-2 pb-4">
            {content(close)}
          </div>
          <div className="shrink-0 px-5 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] border-t border-slate-200/70 dark:border-white/10">
            {footer(close)}
          </div>
        </div>
      )}
    </Modal>
  );
};
