// src/components/RecommendedArtists.tsx
/**
 * "Recommended for you" on the Browse page: YouTube Music's similar artists
 * of the artists you like, most mentioned first (backend/services/recommendations.py).
 * Until you like one, it says how. Visitors can't like artists, so they
 * only get the fallback.
 *
 * Members and admins can dismiss one ("not interested", for them only,
 * undoable from the toast) and restore dismissed ones from the "Dismissed (n)" list.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
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
import { MediaCard } from './MediaCard';
import { Artwork } from './ui/Artwork';
import { Button } from './ui/Button';
import { Modal } from './ui/Modal';
import { SectionHeader } from './ui/SectionHeader';
import { Toast } from './ui/Toast';
import { createMemoryCache, artistPath } from '../utils';
import { Icon } from './ui/icons';

interface ToastState {
  message: string;
  type: 'success' | 'error';
  action?: { label: string; onClick: () => void };
}

/** The last list shown: back on the page it's there right away, then refreshed */
const cache = createMemoryCache<{ recommendations: RecommendedArtist[]; likedCount: number; dismissedCount: number }>(1);
const CACHE_KEY = 'recommendations';

interface RecommendedArtistsProps {
  /** Shown when there's nothing to recommend and nothing dismissed (above how to get some, while you like no artist) */
  fallback?: React.ReactNode;
}

export const RecommendedArtists: React.FC<RecommendedArtistsProps> = ({ fallback = null }) => {
  const { t, locale } = useI18n();
  const { user } = useAuth();
  const canEdit = user?.role === 'administrator' || user?.role === 'member';

  const [cached] = useState(() => cache.get(CACHE_KEY));
  const [recommendations, setRecommendations] = useState<RecommendedArtist[] | null>(cached?.recommendations ?? null);
  const [likedCount, setLikedCount] = useState(cached?.likedCount ?? 0);
  const [dismissedCount, setDismissedCount] = useState(cached?.dismissedCount ?? 0);
  const [showDismissed, setShowDismissed] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);
  const closeToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    try {
      const data = await getRecommendations();
      setRecommendations(data.recommendations);
      setLikedCount(data.liked_count);
      setDismissedCount(data.dismissed_count);
    } catch (err) {
      console.error('Failed to load recommendations:', err);
      setRecommendations((current) => current ?? []);
    }
  }, []);

  useEffect(() => { if (canEdit) load(); }, [load, canEdit]);

  // Dismissals and restores included
  useEffect(() => {
    if (recommendations) cache.set(CACHE_KEY, { recommendations, likedCount, dismissedCount });
  }, [recommendations, likedCount, dismissedCount]);

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

  if (!canEdit) return <>{fallback}</>;
  if (recommendations === null) return null;
  if (recommendations.length === 0 && dismissedCount === 0) {
    if (likedCount > 0) return <>{fallback}</>;
    return (
      <div className="space-y-12">
        {fallback}
        <section>
          <SectionHeader className="!mb-2">{t('browse.recommendations.title')}</SectionHeader>
          <p className="text-sm text-muted-foreground">{t('browse.recommendations.noLikes')}</p>
        </section>
      </div>
    );
  }

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
              <MediaCard
                key={rec.id}
                id={rec.id}
                title={rec.name}
                subtitle={text.short}
                subtitleTitle={text.full}
                subtitleWrap
                thumbnail={getImageUrl(rec.thumbnail)}
                type="artist"
                to={artistPath(rec.id)}
                titleAction={canEdit && (
                  // Next to the name, like the library's heart; shown on hover where there is one
                  <button
                    type="button"
                    onClick={() => dismiss(rec)}
                    aria-label={`${t('browse.recommendations.dismiss')}: ${rec.name}`}
                    title={t('browse.recommendations.dismiss')}
                    className="flex w-7 h-7 items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-slate-200/70 dark:hover:bg-white/10 transition-all outline-none focus-visible:ring-2 focus-visible:ring-accent-500/70 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100"
                  >
                    <Icon name="close" strokeWidth={2.5} className="w-4 h-4" />
                  </button>
                )}
              />
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

  const restore = async (artistId: string) => {
    setRestoring(artistId);
    await onRestore(artistId);
    setDismissed((current) => current?.filter((a) => a.id !== artistId) ?? null);
    setRestoring(null);
  };

  return (
    <Modal
      title={t('browse.recommendations.dismissedTitle')}
      onClose={onClose}
      className="flex flex-col"
    >
      <p className="text-sm text-muted-foreground -mt-4 mb-5">{t('browse.recommendations.dismissedDescription')}</p>

      <div className="overflow-y-auto -mx-2 px-2">
        {dismissed === null ? null : dismissed.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">{t('browse.recommendations.noDismissed')}</p>
        ) : (
          <ul className="space-y-2">
            {dismissed.map((artist) => (
              <li key={artist.id} className="flex items-center gap-3 rounded-2xl p-2 hover:bg-slate-100/60 dark:hover:bg-white/5 transition-colors">
                <Link
                  to={artistPath(artist.id)}
                  className="flex flex-1 min-w-0 items-center gap-3 text-left"
                >
                  <Artwork
                    src={getImageUrl(artist.thumbnail)}
                    name={artist.name}
                    seed={artist.id}
                    className="w-11 h-11 flex-shrink-0 rounded-full overflow-hidden ring-1 ring-slate-900/5 dark:ring-white/10"
                  />
                  <span className="font-medium text-foreground truncate">{artist.name}</span>
                </Link>
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
    </Modal>
  );
};

