// src/components/ui/FollowChartModal.tsx
import React, { useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from './Button';
import { Modal } from './Modal';
import { ErrorBanner } from './PageStatus';
import * as chartsApi from '../../api/charts';
import { CHART_MAX_ARTISTS, useCountryName } from '../../config/charts';
import type { ChartCountry } from '../../config/charts';
import { apiErrorMessage } from '../../utils';

const QUICK_SELECT_VALUES = [5, 10, 20, 30, CHART_MAX_ARTISTS];

interface FollowChartModalProps {
  country: ChartCountry;
  onClose: () => void;
  onSuccess: () => void;
}

export const FollowChartModal: React.FC<FollowChartModalProps> = ({ country, onClose, onSuccess }) => {
  const [topNArtists, setTopNArtists] = useState(CHART_MAX_ARTISTS);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { t } = useI18n();
  const countryName = useCountryName();

  const sliderPercent = ((topNArtists - 1) / (CHART_MAX_ARTISTS - 1)) * 100;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await chartsApi.followChart(country.code, topNArtists);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(apiErrorMessage(err, t, t('common.error')));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={t('charts.followChart')} onClose={onClose} dismissible={!loading}>
      <form onSubmit={handleSubmit} className="space-y-5">
        {error && <ErrorBanner>{error}</ErrorBanner>}

        {/* Country */}
        <div className="glass rounded-2xl p-4 flex items-center gap-4">
          <span className="text-4xl leading-none" aria-hidden="true">{country.flag}</span>
          <div className="min-w-0">
            <h3 className="font-semibold text-foreground truncate">{countryName(country.code)}</h3>
            <p className="text-xs text-muted-foreground mt-0.5">{t('charts.musicChart')}</p>
          </div>
        </div>

        {/* Artist count */}
        <div className="glass rounded-2xl p-5 space-y-5">
          <div className="flex items-center justify-between">
            <label htmlFor="chart-top-n" className="text-sm font-semibold text-foreground">
              {t('charts.numberOfArtists')}
            </label>
            <div className="flex items-center gap-2 bg-blue-500/10 dark:bg-red-500/10 rounded-xl px-3 py-1.5 border border-blue-500/20 dark:border-red-500/20">
              <span className="text-xs text-muted-foreground">{t('charts.top')}</span>
              <span className="text-xl font-bold text-gradient leading-none">{topNArtists}</span>
            </div>
          </div>

          <div>
            <input
              id="chart-top-n"
              type="range"
              min="1"
              max={CHART_MAX_ARTISTS}
              value={topNArtists}
              onChange={(e) => setTopNArtists(parseInt(e.target.value))}
              className="w-full h-2 rounded-full appearance-none cursor-pointer"
              style={{
                background: `linear-gradient(to right, rgb(59,130,246) 0%, rgb(59,130,246) ${sliderPercent}%, rgb(226,232,240) ${sliderPercent}%, rgb(226,232,240) 100%)`,
              }}
            />
            <div className="flex justify-between mt-1.5 text-xs text-muted-foreground">
              <span>1</span>
              <span>{CHART_MAX_ARTISTS}</span>
            </div>
          </div>

          <div className="flex gap-2 flex-wrap">
            {QUICK_SELECT_VALUES.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setTopNArtists(value)}
                className={`flex-1 min-w-0 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                  topNArtists === value
                    ? 'bg-blue-600 dark:bg-red-600 text-white shadow-md'
                    : 'bg-slate-100 dark:bg-white/10 text-muted-foreground hover:bg-slate-200 dark:hover:bg-white/20'
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </div>

        <p className="text-xs text-muted-foreground px-1">{t('charts.storageWarning')}</p>

        <div className="flex gap-3 pt-1">
          <Button type="button" variant="ghost" onClick={onClose} disabled={loading} className="flex-1">
            {t('common.cancel')}
          </Button>
          <Button type="submit" variant="primary" isLoading={loading} className="flex-1">
            {t('charts.followChart')}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
