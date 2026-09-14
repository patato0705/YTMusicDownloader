// src/components/MediaList.tsx
import React, { useState } from 'react';
import { useI18n } from '../contexts/I18nContext';
import { STATUS_BADGES, albumTypeKey, PLACEHOLDER } from './MediaCard';
import type { MediaStatus } from '../types';

export type MediaListKind = 'artist' | 'album';

// Column widths are shared by the header and the rows so they line up. Columns
// appear as the viewport grows: phones get thumb + title + status pip, `sm` adds
// the track progress, `lg` the text columns (and the header), `xl` the date.
const COLUMNS = {
  artist: 'hidden lg:block w-44 xl:w-56 2xl:w-72 shrink-0',
  albums: 'hidden lg:block w-16 shrink-0 text-right',
  type: 'hidden lg:block w-16 shrink-0',
  year: 'hidden lg:block w-12 shrink-0',
  tracks: 'hidden sm:block w-36 xl:w-52 shrink-0',
  date: 'hidden xl:block w-28 shrink-0',
  status: 'w-6 lg:w-32 shrink-0',
};

const HEADER_CELL = 'text-[11px] font-semibold uppercase tracking-wider text-muted-foreground truncate';

interface MediaListProps {
  kind: MediaListKind;
  children: React.ReactNode;
  className?: string;
}

/** Glass panel holding MediaRows of one kind, with a column header on large screens */
export const MediaList: React.FC<MediaListProps> = ({ kind, children, className = '' }) => {
  const { t } = useI18n();
  const isArtist = kind === 'artist';

  return (
    <div className={`glass rounded-2xl overflow-hidden ${className}`}>
      <div className="hidden lg:flex items-center gap-4 px-4 py-2 border-b border-slate-200/60 dark:border-white/10 bg-slate-50/60 dark:bg-white/[0.03]">
        {/* Spacer matching the thumbnail column */}
        <div className="w-12 shrink-0" />
        <div className={`flex-1 min-w-0 ${HEADER_CELL}`}>{t('library.columns.name')}</div>
        {isArtist ? (
          <div className={`${COLUMNS.albums} ${HEADER_CELL}`}>{t('library.columns.albums')}</div>
        ) : (
          <>
            <div className={`${COLUMNS.artist} ${HEADER_CELL}`}>{t('library.columns.artist')}</div>
            <div className={`${COLUMNS.type} ${HEADER_CELL}`}>{t('library.columns.type')}</div>
            <div className={`${COLUMNS.year} ${HEADER_CELL}`}>{t('library.columns.year')}</div>
          </>
        )}
        <div className={`${COLUMNS.tracks} ${HEADER_CELL}`}>{t('library.columns.tracks')}</div>
        <div className={`${COLUMNS.date} ${HEADER_CELL}`}>
          {t(isArtist ? 'library.columns.followed' : 'library.columns.added')}
        </div>
        <div className={`${COLUMNS.status} ${HEADER_CELL}`}>{t('library.columns.status')}</div>
      </div>

      <div className="divide-y divide-slate-200/60 dark:divide-white/10">{children}</div>
    </div>
  );
};

interface MediaRowProps {
  id: string;
  title: string;
  /** Artist name - albums only */
  subtitle?: string;
  thumbnail?: string;
  type: MediaListKind;
  albumType?: string;
  year?: string;
  mediaStatus?: MediaStatus;
  albumsCount?: number;
  tracksTotal?: number;
  tracksDownloaded?: number;
  /** ISO timestamp of when the item joined the library */
  date?: string | null;
  onClick?: () => void;
}

function formatDate(iso: string | null | undefined, locale: string): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'short', day: 'numeric' }).format(date);
}

export const MediaRow: React.FC<MediaRowProps> = ({
  title,
  subtitle,
  thumbnail,
  type,
  albumType,
  year,
  mediaStatus,
  albumsCount,
  tracksTotal,
  tracksDownloaded,
  date,
  onClick,
}) => {
  const { t, locale } = useI18n();
  const [imageError, setImageError] = useState(false);

  const isArtist = type === 'artist';
  const status = mediaStatus ? STATUS_BADGES[mediaStatus] : undefined;
  const typeLabel = isArtist ? null : t(albumTypeKey(albumType));

  const total = tracksTotal ?? 0;
  const downloaded = tracksDownloaded ?? 0;
  const hasTracks = total > 0;
  const complete = hasTracks && downloaded >= total;
  const progress = hasTracks ? Math.min(100, Math.round((downloaded / total) * 100)) : 0;
  const tracksText = hasTracks ? `${downloaded}/${total}` : '—';

  // Everything that has no column at the current width gets folded into the
  // line under the title, so no info is lost on small screens.
  const compactMeta = isArtist
    ? t(albumsCount === 1 ? 'library.meta.albumCountOne' : 'library.meta.albumCount', { count: albumsCount ?? 0 })
    : [subtitle, year, typeLabel].filter(Boolean).join(' · ');

  return (
    <button
      type="button"
      onClick={onClick}
      className="group w-full flex items-center gap-3 md:gap-4 px-3 md:px-4 py-2.5 text-left outline-none transition-colors duration-200 hover:bg-slate-100/70 dark:hover:bg-white/5 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500/70 dark:focus-visible:ring-red-500/70"
    >
      {/* Artwork */}
      <div
        className={`relative w-11 h-11 md:w-12 md:h-12 shrink-0 overflow-hidden bg-slate-200 dark:bg-zinc-800 ring-1 ring-slate-900/5 dark:ring-white/10 ${
          isArtist ? 'rounded-full' : 'rounded-lg'
        }`}
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
      </div>

      {/* Title + compact meta */}
      <div className="flex-1 min-w-0">
        <h3 className="font-semibold text-sm text-foreground truncate transition-colors group-hover:text-blue-600 dark:group-hover:text-red-400">
          {title}
        </h3>
        <p className="text-xs text-muted-foreground truncate lg:hidden">
          {compactMeta}
          <span className="sm:hidden">
            {compactMeta && ' · '}
            {t('library.meta.trackCount', { count: tracksText })}
          </span>
        </p>
      </div>

      {/* Large-screen columns */}
      {isArtist ? (
        <div className={`${COLUMNS.albums} text-sm tabular-nums text-muted-foreground`}>{albumsCount ?? 0}</div>
      ) : (
        <>
          <div className={`${COLUMNS.artist} text-sm text-muted-foreground truncate`}>{subtitle || '—'}</div>
          <div className={COLUMNS.type}>
            <span className="inline-block rounded-full bg-slate-200/70 dark:bg-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {typeLabel}
            </span>
          </div>
          <div className={`${COLUMNS.year} text-sm tabular-nums text-muted-foreground`}>{year || '—'}</div>
        </>
      )}

      {/* Track progress */}
      <div className={COLUMNS.tracks}>
        <div className="flex items-center gap-2">
          <div className="h-1.5 flex-1 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
            <div
              className={`h-full rounded-full transition-[width] duration-500 ${
                complete ? 'bg-emerald-500' : 'bg-blue-600 dark:bg-red-600'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="w-14 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{tracksText}</span>
        </div>
      </div>

      {/* Date */}
      <div className={`${COLUMNS.date} text-sm text-muted-foreground truncate`}>{formatDate(date, locale)}</div>

      {/* Status - a pip on small screens, pip + label from lg up */}
      <div className={`${COLUMNS.status} flex items-center gap-2`}>
        {status && (
          <>
            <span
              className={`flex w-6 h-6 shrink-0 items-center justify-center rounded-full ${status.className} shadow-sm ring-2 ring-white dark:ring-zinc-900`}
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
            <span className="hidden lg:inline text-xs font-medium text-muted-foreground truncate">
              {t(status.labelKey)}
            </span>
          </>
        )}
      </div>
    </button>
  );
};
