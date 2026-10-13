// src/components/LibraryStatCards.tsx
import { useI18n } from '../contexts/I18nContext';
import type { LibraryStats } from '../api/library';
import { Spinner } from './ui/Spinner';
import { StatCard } from './ui/StatCard';
import { formatNumber } from '../utils';

const icon = (emoji: string) => <span className="text-2xl" aria-hidden="true">{emoji}</span>;

/**
 * The library in four numbers, on Home and Library: followed artists, albums
 * in the library, downloaded tracks, disk usage. Spinners while `loading`.
 */
export function LibraryStatCards({ stats, loading = false }: { stats: LibraryStats | null; loading?: boolean }): JSX.Element {
  const { t, formatLocale } = useI18n();
  const show = (value: (s: LibraryStats) => string) => (stats ? value(stats) : loading ? <Spinner size="sm" /> : '-');

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatCard
        icon={icon('🎤')}
        label={t('library.stats.artists')}
        value={show((s) => formatNumber(s.artists.total, formatLocale))}
      />
      <StatCard
        icon={icon('💿')}
        label={t('library.stats.albums')}
        value={show((s) => formatNumber(s.albums.downloaded, formatLocale))}
      />
      <StatCard
        icon={icon('🎵')}
        label={t('library.stats.tracks')}
        value={show((s) => formatNumber(s.tracks.downloaded, formatLocale))}
      />
      <StatCard
        icon={icon('⚡')}
        label={t('library.stats.diskUsage')}
        value={show((s) => `${s.storage.gb.toLocaleString(formatLocale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`)}
        info={t('library.stats.diskUsageInfo')}
      />
    </div>
  );
}
