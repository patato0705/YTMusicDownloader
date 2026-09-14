// src/components/MediaCard.tsx
import React, { useState } from 'react';
import { useI18n } from '../contexts/I18nContext';
import type { MediaStatus } from '../types';

export type { MediaStatus };
export type MediaKind = 'artist' | 'album' | 'track';

interface MediaCardProps {
  id: string;
  title: string;
  subtitle?: string;
  thumbnail?: string;
  type?: MediaKind;
  /** Release type as reported by YTMusic ("Album", "EP", "Single") - only used when type is 'album' */
  albumType?: string;
  year?: string;
  mediaStatus?: MediaStatus;
  /** Why this item is in the results when it didn't match by name (e.g. a track inside it did) */
  matchHint?: string;
  onClick?: () => void;
  className?: string;
}

export const PLACEHOLDER = '/assets/placeholder-music.png';

/** Status pip shown on the artwork - one entry per status, so the markup stays in one place */
export const STATUS_BADGES: Record<NonNullable<MediaStatus>, {
  labelKey: string;
  className: string;
  iconClassName?: string;
  path: string;
}> = {
  downloaded: {
    labelKey: 'mediaCard.status.downloaded',
    className: 'bg-emerald-500',
    path: 'M5 13l4 4L19 7',
  },
  in_library: {
    labelKey: 'mediaCard.status.inLibrary',
    className: 'bg-blue-500 dark:bg-red-600',
    path: 'M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z',
  },
  downloading: {
    labelKey: 'mediaCard.status.downloading',
    className: 'bg-amber-500',
    iconClassName: 'animate-spin',
    path: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
  },
  queued: {
    labelKey: 'mediaCard.status.queued',
    className: 'bg-slate-500 dark:bg-zinc-600',
    path: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  // Dark mode already uses red as its accent (see in_library), so this leans
  // on the "!" glyph and a pinker shade to stay tellable apart from it
  failed: {
    labelKey: 'mediaCard.status.failed',
    className: 'bg-red-600 dark:bg-rose-500',
    path: 'M12 8v5m0 3.5h.01',
  },
};

/** Release type of an album, falling back to "Album" for anything unexpected */
export function albumTypeKey(albumType?: string): string {
  switch (albumType?.trim().toLowerCase()) {
    case 'single':
      return 'mediaCard.type.single';
    case 'ep':
      return 'mediaCard.type.ep';
    default:
      return 'mediaCard.type.album';
  }
}

const MediaCard: React.FC<MediaCardProps> = ({
  title,
  subtitle,
  thumbnail,
  type = 'album',
  albumType,
  year,
  mediaStatus,
  matchHint,
  onClick,
  className = '',
}) => {
  const { t } = useI18n();
  const [imageError, setImageError] = useState(false);

  const isArtist = type === 'artist';
  const status = mediaStatus ? STATUS_BADGES[mediaStatus] : undefined;
  const meta = [subtitle, year].filter(Boolean).join(' · ');

  // Artists are already told apart by their round artwork (and live in their own
  // sections), so the badge would only crowd the circle - square artwork keeps it
  const typeLabel = isArtist
    ? null
    : type === 'track'
      ? t('mediaCard.type.track')
      : t(albumTypeKey(albumType));

  const shape = isArtist ? 'rounded-full' : 'rounded-2xl';
  // A circle has no corner to pin the status pip to, so sit it on the edge instead
  const statusBadgePosition = isArtist ? 'bottom-[6%] left-[6%]' : 'bottom-2 left-2';

  return (
    <button
      type="button"
      onClick={onClick}
      className={`group w-full text-left rounded-2xl outline-none transition-transform duration-300 hover:-translate-y-1 focus-visible:ring-2 focus-visible:ring-blue-500/70 dark:focus-visible:ring-red-500/70 ${className}`}
    >
      {/* Artwork - the badges live outside the clipping box so they survive the round shape */}
      <div className="relative mb-3">
        <div
          className={`relative aspect-square overflow-hidden bg-slate-200 dark:bg-zinc-800 shadow-sm ring-1 ring-slate-900/5 dark:ring-white/10 transition-shadow duration-300 group-hover:shadow-xl group-hover:shadow-blue-500/10 dark:group-hover:shadow-red-500/10 ${shape}`}
        >
          <img
            src={imageError ? PLACEHOLDER : thumbnail || PLACEHOLDER}
            alt={title}
            loading="lazy"
            className="w-full h-full object-cover transition-transform duration-500 ease-out group-hover:scale-105"
            onError={() => {
              if (!imageError) {
                setImageError(true);
              }
            }}
          />

          {/* Subtle darkening on hover, keeps the badges readable */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/50 via-black/5 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
        </div>

        {/* Type badge */}
        {typeLabel && (
          <span className="pointer-events-none absolute z-10 top-2 right-2 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white shadow-sm ring-1 ring-white/20 backdrop-blur-md">
            {typeLabel}
          </span>
        )}

        {/* Status badge */}
        {status && (
          <span
            className={`absolute z-10 ${statusBadgePosition} flex w-6 h-6 items-center justify-center rounded-full ${status.className} shadow-md ring-2 ring-white dark:ring-zinc-900`}
            title={t(status.labelKey)}
          >
            <svg
              className={`w-3.5 h-3.5 text-white ${status.iconClassName || ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d={status.path} />
            </svg>
          </span>
        )}
      </div>

      {/* Text content - centered for artists */}
      <div className={`space-y-0.5 px-0.5 ${isArtist ? 'text-center' : ''}`}>
        <h3 className="font-semibold text-sm text-foreground truncate transition-colors group-hover:text-blue-600 dark:group-hover:text-red-400">
          {title}
        </h3>

        {meta && <p className="text-xs text-muted-foreground truncate">{meta}</p>}

        {matchHint && (
          <p className="text-xs text-blue-600 dark:text-red-400 truncate" title={matchHint}>
            {matchHint}
          </p>
        )}
      </div>
    </button>
  );
};

export default MediaCard;
