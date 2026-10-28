// src/components/MediaCard.tsx
import React from 'react';
import { Link } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { Artwork } from './ui/Artwork';
import type { MediaStatus } from '../types';
import { ICON_PATHS } from './ui/icons';

export type MediaKind = 'artist' | 'album' | 'track';

interface MediaCardProps {
  id: string;
  title: string;
  subtitle?: string;
  /** Hover text for the subtitle line, when it's a shortened form of something longer */
  subtitleTitle?: string;
  /** Let the subtitle wrap to a second line instead of cutting it short */
  subtitleWrap?: boolean;
  /** Makes the subtitle a link of its own (e.g. an album's artist) */
  subtitleTo?: string;
  thumbnail?: string;
  type?: MediaKind;
  /** Release type as reported by YTMusic ("Album", "EP", "Single"), only used when type is 'album' */
  albumType?: string;
  year?: string;
  mediaStatus?: MediaStatus;
  /** Why this item is in the results when it didn't match by name (e.g. a track inside it did) */
  matchHint?: string;
  /** Page the card opens: renders a real link (middle-click, open in new tab) */
  to?: string;
  onClick?: () => void;
  /** A small button right after the title (e.g. a like) */
  titleAction?: React.ReactNode;
  className?: string;
}

/** The look of each status pip */
const STATUS_BADGES: Record<NonNullable<MediaStatus>, {
  labelKey: string;
  className: string;
  iconClassName?: string;
  path: string;
}> = {
  downloaded: {
    labelKey: 'mediaCard.status.downloaded',
    className: 'bg-emerald-500',
    path: ICON_PATHS.check,
  },
  in_library: {
    labelKey: 'mediaCard.status.inLibrary',
    className: 'bg-accent-500 dark:bg-accent-600',
    path: ICON_PATHS.bookmark,
  },
  downloading: {
    labelKey: 'mediaCard.status.downloading',
    className: 'bg-amber-500',
    iconClassName: 'animate-spin',
    path: ICON_PATHS.refresh,
  },
  queued: {
    labelKey: 'mediaCard.status.queued',
    className: 'bg-slate-500 dark:bg-zinc-600',
    path: ICON_PATHS.clock,
  },
  failed: {
    labelKey: 'mediaCard.status.failed',
    className: 'bg-red-600 dark:bg-red-500',
    path: ICON_PATHS.alert,
  },
};

/** Round badge telling a media status apart by colour and icon, with its name on hover */
export const StatusPip: React.FC<{ status: NonNullable<MediaStatus>; className?: string }> = ({ status, className = '' }) => {
  const { t } = useI18n();
  const badge = STATUS_BADGES[status];
  return (
    <span
      className={`flex w-6 h-6 shrink-0 items-center justify-center rounded-full ${badge.className} ${className}`}
      title={t(badge.labelKey)}
    >
      <svg className={`w-3.5 h-3.5 text-white ${badge.iconClassName || ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d={badge.path} />
      </svg>
    </span>
  );
};

/** Translation key of a status's name */
export const statusLabelKey = (status: NonNullable<MediaStatus>): string => STATUS_BADGES[status].labelKey;

/**
 * Opens a card's or row's page through a link (or button) stretched over it,
 * rather than the card being one: then it can still hold controls of its own
 * (a like, the artist link). Content after it goes pointer-events-none, and those
 * controls pointer-events-auto above it.
 */
export const CardLink: React.FC<{ to?: string; onClick?: () => void; label: string; className?: string }> = ({
  to,
  onClick,
  label,
  className = '',
}) => {
  const classes = `absolute inset-0 outline-none focus-visible:ring-2 focus-visible:ring-accent-500/70 ${className}`;
  return to ? (
    <Link to={to} onClick={onClick} aria-label={label} className={classes} />
  ) : (
    <button type="button" onClick={onClick} aria-label={label} className={classes} />
  );
};

/** A link inside a card / row (e.g. the artist under an album), above its CardLink */
export const SubtitleLink: React.FC<{ to: string; children: React.ReactNode }> = ({ to, children }) => (
  <Link
    to={to}
    className="relative z-10 pointer-events-auto cursor-pointer rounded-sm outline-none hover:text-accent-600 dark:hover:text-accent-400 hover:underline focus-visible:underline focus-visible:text-accent-600 dark:focus-visible:text-accent-400 transition-colors"
  >
    {children}
  </Link>
);

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

export const MediaCard: React.FC<MediaCardProps> = ({
  id,
  title,
  subtitle,
  subtitleTitle,
  subtitleWrap = false,
  subtitleTo,
  thumbnail,
  type = 'album',
  albumType,
  year,
  mediaStatus,
  matchHint,
  to,
  onClick,
  titleAction,
  className = '',
}) => {
  const { t } = useI18n();
  const isArtist = type === 'artist';

  // Artists are already told apart by their round artwork (and live in their own
  // sections), so they go without; the others name their type under the title
  const typeLabel = isArtist
    ? null
    : type === 'track'
      ? t('mediaCard.type.track')
      : t(albumTypeKey(albumType));
  // A circle leaves no corner for a pip, so an artist's status is a dot and a word under the name
  const artistStatus = isArtist && mediaStatus ? mediaStatus : null;
  const hasMeta = Boolean(subtitle || year || typeLabel || artistStatus);

  const shape = isArtist ? 'rounded-full' : 'rounded-2xl';

  return (
    <div className={`group relative w-full text-left rounded-2xl transition-transform duration-300 hover:-translate-y-1 ${className}`}>
      <CardLink to={to} onClick={onClick} label={title} className="rounded-2xl" />
      <div className="relative pointer-events-none">
        {/* Artwork: the badges live outside the clipping box so they survive the round shape */}
        <div className="relative mb-3">
          <div
            className={`relative aspect-square overflow-hidden bg-slate-200 dark:bg-zinc-800 shadow-sm ring-1 ring-slate-900/5 dark:ring-white/10 transition-shadow duration-300 group-hover:shadow-xl group-hover:shadow-accent-500/10 ${shape}`}
          >
            <Artwork
              src={thumbnail}
              name={title}
              seed={id}
              className="w-full h-full transition-transform duration-500 ease-out group-hover:scale-105"
            />

            {/* Subtle darkening on hover, keeps the status pip readable */}
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/50 via-black/5 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
          </div>

          {mediaStatus && !isArtist && (
            <StatusPip
              status={mediaStatus}
              className="absolute z-10 bottom-2 left-2 shadow-md ring-2 ring-white dark:ring-zinc-900"
            />
          )}
        </div>

        {/* Text content, centered for artists */}
        <div className={`space-y-0.5 px-0.5 ${isArtist ? 'text-center' : ''}`}>
          {/* Centred names sit in the middle column, so an action beside them doesn't pull them off centre */}
          <div className={isArtist ? 'grid grid-cols-[1fr_minmax(0,auto)_1fr] items-center gap-1' : 'flex items-center gap-1'}>
            <h3 className={`min-w-0 font-semibold text-sm text-foreground truncate transition-colors group-hover:text-accent-600 dark:group-hover:text-accent-400 ${isArtist ? 'col-start-2' : ''}`}>
              {title}
            </h3>
            {titleAction && <div className="relative z-10 shrink-0 -my-1 pointer-events-auto justify-self-start">{titleAction}</div>}
          </div>

          {hasMeta && (
            <p className={`text-xs text-muted-foreground ${subtitleWrap ? 'line-clamp-2' : 'truncate'}`} title={subtitleTitle}>
              {artistStatus && (
                <>
                  <span className={`inline-block w-2 h-2 mr-1 rounded-full align-middle ${STATUS_BADGES[artistStatus].className}`} aria-hidden="true" />
                  {t(statusLabelKey(artistStatus))}
                  {subtitle && ' · '}
                </>
              )}
              {subtitle && (subtitleTo ? <SubtitleLink to={subtitleTo}>{subtitle}</SubtitleLink> : subtitle)}
              {subtitle && year && ' · '}
              {year}
              {(subtitle || year) && typeLabel && ' · '}
              {typeLabel}
            </p>
          )}

          {matchHint && (
            <p className="text-xs text-accent-600 dark:text-accent-400 truncate" title={matchHint}>
              {matchHint}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

