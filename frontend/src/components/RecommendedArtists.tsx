// src/components/RecommendedArtists.tsx
/**
 * "Recommended for you" on the Browse page: YouTube Music's similar artists
 * of the artists you follow, most mentioned first (backend/services/recommendations.py).
 *
 * Members and admins can dismiss one ("not interested", undoable from the
 * toast) and restore dismissed ones from the "Dismissed (n)" list.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { useAuth } from '../contexts/AuthContext';
import {
  getRecommendations,
  getDismissedArtists,
  dismissArtist,
  restoreArtist,
} from '../api/recommendations';
import type { RecommendedArtist, DismissedArtist } from '../api/recommendations';
import { getImageUrl } from '../api/media';
import MediaCard from './MediaCard';
import { Artwork } from './ui/Artwork';
import { Button } from './ui/Button';
import { SectionHeader } from './ui/SectionHeader';
import { Toast } from './ui/Toast';
import { createMemoryCache } from '../utils';

interface ToastState {
  message: string;
  type: 'success' | 'error';
  action?: { label: string; onClick: () => void };
}

/** The last list shown: back on the page it's there right away, then refreshed */
const cache = createMemoryCache<{ recommendations: RecommendedArtist[]; dismissedCount: number }>(1);
const CACHE_KEY = 'recommendations';

interface RecommendedArtistsProps {
  /** Shown instead when there's nothing to recommend and nothing dismissed */
  fallback?: React.ReactNode;
}

export const RecommendedArtists: React.FC<RecommendedArtistsProps> = ({ fallback = null }) => {
  const { t, locale } = useI18n();
  const { user } = useAuth();
  const navigate = useNavigate();
  const canEdit = user?.role === 'administrator' || user?.role === 'member';

  const [cached] = useState(() => cache.get(CACHE_KEY));
  const [recommendations, setRecommendations] = useState<RecommendedArtist[] | null>(cached?.recommendations ?? null);
  const [dismissedCount, setDismissedCount] = useState(cached?.dismissedCount ?? 0);
  const [showDismissed, setShowDismissed] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);
  const closeToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    try {
      const data = await getRecommendations();
      setRecommendations(data.recommendations);
      setDismissedCount(data.dismissed_count);
    } catch (err) {
      console.error('Failed to load recommendations:', err);
      setRecommendations((current) => current ?? []);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Dismissals and restores included
  useEffect(() => {
    if (recommendations) cache.set(CACHE_KEY, { recommendations, dismissedCount });
  }, [recommendations, dismissedCount]);

  const listFormat = useMemo(() => new Intl.ListFormat(locale, { type: 'conjunction' }), [locale]);
  const similarTo = (rec: RecommendedArtist) => {
    const names = listFormat.format(rec.similar_to.map((a) => a.name));
    return {
      short: rec.count <= 2 ? t('browse.recommendations.similarTo', { names }) : t('browse.recommendations.similarToMany', { count: rec.count }),
      full: t('browse.recommendations.similarTo', { names }),
    };
  };

  const restore = async (artistId: string) => {
    try {
      await restoreArtist(artistId);
    } catch (err) {
      console.error('Failed to restore artist:', err);
      setToast({ message: t('browse.recommendations.error'), type: 'error' });
    }
    await load();
  };

  const dismiss = async (rec: RecommendedArtist) => {
    // Gone right away; put back if the server says no
    setRecommendations((current) => current?.filter((r) => r.id !== rec.id) ?? null);
    try {
      await dismissArtist(rec.id);
      setDismissedCount((n) => n + 1);
      setToast({
        message: t('browse.recommendations.dismissedToast', { name: rec.name }),
        type: 'success',
        action: { label: t('browse.recommendations.undo'), onClick: () => restore(rec.id) },
      });
    } catch (err) {
      console.error('Failed to dismiss artist:', err);
      setToast({ message: t('browse.recommendations.error'), type: 'error' });
      await load();
    }
  };

  if (recommendations === null) return null;
  if (recommendations.length === 0 && dismissedCount === 0) return <>{fallback}</>;

  return (
    <section>
      <SectionHeader className="!mb-2">{t('browse.recommendations.title')}</SectionHeader>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 mb-6">
        <p className="text-sm text-muted-foreground">{t('browse.recommendations.subtitle')}</p>
        {canEdit && dismissedCount > 0 && (
          <button
            type="button"
            onClick={() => setShowDismissed(true)}
            className="text-sm text-muted-foreground hover:text-foreground underline-offset-4 hover:underline transition-colors"
          >
            {t('browse.recommendations.dismissedLink', { count: dismissedCount })}
          </button>
        )}
      </div>

      {recommendations.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('browse.recommendations.noneLeft')}</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {recommendations.map((rec) => {
            const text = similarTo(rec);
            return (
              <div key={rec.id} className="relative group/rec">
                <MediaCard
                  id={rec.id}
                  title={rec.name}
                  subtitle={text.short}
                  subtitleTitle={text.full}
                  subtitleWrap
                  thumbnail={getImageUrl(rec.thumbnail)}
                  type="artist"
                  onClick={() => navigate(`/artists/${encodeURIComponent(rec.id)}`)}
                />
                {canEdit && (
                  // Outside the card (a button can't hold another), over the
                  // artwork's top-right corner, which the round picture leaves free
                  <button
                    type="button"
                    onClick={() => dismiss(rec)}
                    aria-label={`${t('browse.recommendations.dismiss')}: ${rec.name}`}
                    title={t('browse.recommendations.dismiss')}
                    className="absolute top-0 right-0 z-20 flex w-8 h-8 items-center justify-center rounded-full bg-black/55 text-white shadow-md ring-1 ring-white/20 backdrop-blur-md transition-all duration-300 hover:bg-black/75 group-hover/rec:-translate-y-1 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/rec:opacity-100 focus-visible:opacity-100"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {showDismissed && (
        <DismissedArtistsModal
          onClose={() => setShowDismissed(false)}
          onRestore={restore}
        />
      )}

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          action={toast.action}
          duration={toast.action ? 6000 : 3000}
          onClose={closeToast}
        />
      )}
    </section>
  );
};

interface DismissedArtistsModalProps {
  onClose: () => void;
  onRestore: (artistId: string) => Promise<void>;
}

const DismissedArtistsModal: React.FC<DismissedArtistsModalProps> = ({ onClose, onRestore }) => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState<DismissedArtist[] | null>(null);
  const [restoring, setRestoring] = useState<string | null>(null);

  useEffect(() => {
    getDismissedArtists()
      .then((data) => setDismissed(data.dismissed))
      .catch((err) => {
        console.error('Failed to load dismissed artists:', err);
        setDismissed([]);
      });
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const restore = async (artistId: string) => {
    setRestoring(artistId);
    await onRestore(artistId);
    setDismissed((current) => current?.filter((a) => a.id !== artistId) ?? null);
    setRestoring(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="dismissed-artists-title"
        className="glass rounded-3xl p-6 sm:p-8 max-w-md w-full max-h-[80vh] flex flex-col border-gradient shadow-2xl animate-in fade-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-2">
          <h2 id="dismissed-artists-title" className="text-2xl font-bold text-gradient">
            {t('browse.recommendations.dismissedTitle')}
          </h2>
          <button
            onClick={onClose}
            aria-label={t('common.close')}
            className="w-8 h-8 flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/10 transition-all text-sm"
          >
            ✕
          </button>
        </div>
        <p className="text-sm text-muted-foreground mb-5">{t('browse.recommendations.dismissedDescription')}</p>

        <div className="overflow-y-auto -mx-2 px-2">
          {dismissed === null ? null : dismissed.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">{t('browse.recommendations.noDismissed')}</p>
          ) : (
            <ul className="space-y-2">
              {dismissed.map((artist) => (
                <li key={artist.id} className="flex items-center gap-3 rounded-2xl p-2 hover:bg-slate-100/60 dark:hover:bg-white/5 transition-colors">
                  <button
                    type="button"
                    onClick={() => navigate(`/artists/${encodeURIComponent(artist.id)}`)}
                    className="flex flex-1 min-w-0 items-center gap-3 text-left"
                  >
                    <Artwork
                      src={getImageUrl(artist.thumbnail)}
                      name={artist.name}
                      seed={artist.id}
                      className="w-11 h-11 flex-shrink-0 rounded-full overflow-hidden ring-1 ring-slate-900/5 dark:ring-white/10"
                    />
                    <span className="font-medium text-foreground truncate">{artist.name}</span>
                  </button>
                  <Button
                    size="sm"
                    variant="secondary"
                    isLoading={restoring === artist.id}
                    disabled={restoring !== null}
                    onClick={() => restore(artist.id)}
                  >
                    {t('browse.recommendations.restore')}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default RecommendedArtists;
