// src/components/admin/FollowChartModal.tsx
import React, { useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../ui/Button';
import * as chartsApi from '../../api/charts';
import type { ChartCountry } from '../../config/charts';

const MAX_ARTISTS = 40;
const QUICK_SELECT_VALUES = [5, 10, 20, 30, 40];

interface FollowChartModalProps {
  country: ChartCountry;
  onClose: () => void;
  onSuccess: () => void;
}

export const FollowChartModal: React.FC<FollowChartModalProps> = ({ country, onClose, onSuccess }) => {
  const [topNArtists, setTopNArtists] = useState(MAX_ARTISTS);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { t } = useI18n();

  const sliderPercent = ((topNArtists - 1) / (MAX_ARTISTS - 1)) * 100;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (topNArtists < 1 || topNArtists > MAX_ARTISTS) {
      setError(t('charts.artistCountError'));
      return;
    }

    setLoading(true);

    try {
      await chartsApi.followChart(country.code, topNArtists);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to follow chart');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60">
      <div className="glass rounded-3xl p-8 max-w-md w-full border-gradient shadow-2xl animate-in fade-in zoom-in-95 duration-200">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gradient">
            {t('charts.followChart')}
          </h2>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/10 transition-all text-sm"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">

          {/* Error */}
          {error && (
            <div className="bg-red-500/10 dark:bg-red-500/5 rounded-xl p-3 border border-red-500/20">
              <p className="text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
                <span>⚠️</span> {error}
              </p>
            </div>
          )}

          {/* Country display */}
          <div className="glass rounded-2xl p-4 border border-slate-200/50 dark:border-white/10 flex items-center gap-4">
            <span className="text-4xl leading-none">{country.flag}</span>
            <div className="min-w-0">
              <h3 className="font-semibold text-foreground truncate">{country.name}</h3>
              <p className="text-xs text-muted-foreground mt-0.5">{t('charts.musicChart')}</p>
            </div>
          </div>

          {/* Artist count section */}
          <div className="glass rounded-2xl p-5 border border-slate-200/50 dark:border-white/10 space-y-5">

            {/* Label + badge */}
            <div className="flex items-center justify-between">
              <label className="text-sm font-semibold text-foreground">
                {t('charts.numberOfArtists')}
              </label>
              <div className="flex items-center gap-2 bg-blue-500/10 dark:bg-red-500/10 rounded-xl px-3 py-1.5 border border-blue-500/20 dark:border-red-500/20">
                <span className="text-xs text-muted-foreground">Top</span>
                <span className="text-xl font-bold text-gradient leading-none">{topNArtists}</span>
              </div>
            </div>

            {/* Slider */}
            <div className="relative">
              <input
                type="range"
                min="1"
                max={MAX_ARTISTS}
                value={topNArtists}
                onChange={(e) => setTopNArtists(parseInt(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer"
                style={{
                  background: `linear-gradient(to right, rgb(59,130,246) 0%, rgb(59,130,246) ${sliderPercent}%, rgb(226,232,240) ${sliderPercent}%, rgb(226,232,240) 100%)`,
                }}
              />
              <div className="flex justify-between mt-1.5">
                <span className="text-xs text-muted-foreground">1</span>
                <span className="text-xs text-muted-foreground">{MAX_ARTISTS}</span>
              </div>
            </div>

            {/* Quick-select pills */}
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

          {/* Storage hint */}
          <p className="text-xs text-muted-foreground px-1">
            {t('charts.storageWarning')}
          </p>

          {/* Actions */}
          <div className="flex gap-3 pt-1">
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={loading}
              className="flex-1"
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={loading}
              className="flex-1"
            >
              {t('charts.followChart')}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
