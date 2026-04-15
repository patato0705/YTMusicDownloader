// src/components/admin/FollowChartModal.tsx
import React, { useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../ui/Button';
import * as chartsApi from '../../api/charts';
import type { ChartCountry } from '../../config/charts';

interface FollowChartModalProps {
  country: ChartCountry;
  onClose: () => void;
  onSuccess: () => void;
}

export const FollowChartModal: React.FC<FollowChartModalProps> = ({ country, onClose, onSuccess }) => {
  const [topNArtists, setTopNArtists] = useState(40);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { t } = useI18n();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (topNArtists < 1 || topNArtists > 100) {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="glass rounded-3xl p-8 max-w-md w-full border-gradient shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gradient">
            {t('charts.followChart')}
          </h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors text-xl"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="bg-red-500/10 dark:bg-red-500/5 rounded-xl p-3 border border-red-500/20">
              <p className="text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
                <span>⚠️</span> {error}
              </p>
            </div>
          )}

          {/* Country display */}
          <div className="glass rounded-2xl p-4 border border-slate-200/50 dark:border-white/10">
            <div className="flex items-center gap-3">
              <span className="text-4xl">{country.flag}</span>
              <div>
                <h3 className="font-semibold text-foreground">{country.name}</h3>
                <p className="text-sm text-muted-foreground">{t('charts.musicChart')}</p>
              </div>
            </div>
          </div>

          {/* Top N Artists slider */}
          <div>
            <label className="block text-sm font-semibold text-foreground mb-3">
              {t('charts.numberOfArtists')}
            </label>
            
            <div className="space-y-4">
              {/* Slider */}
              <input
                type="range"
                min="1"
                max="100"
                value={topNArtists}
                onChange={(e) => setTopNArtists(parseInt(e.target.value))}
                className="w-full h-2 rounded-lg appearance-none cursor-pointer bg-slate-200 dark:bg-white/10"
                style={{
                  background: `linear-gradient(to right, rgb(59, 130, 246) 0%, rgb(59, 130, 246) ${topNArtists}%, rgb(226, 232, 240) ${topNArtists}%, rgb(226, 232, 240) 100%)`,
                }}
              />

              {/* Value display */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">{t('charts.trackTopArtists')}</span>
                <div className="glass rounded-xl px-4 py-2 border border-slate-200/50 dark:border-white/10">
                  <span className="text-2xl font-bold text-gradient">{topNArtists}</span>
                </div>
              </div>

              {/* Quick select buttons */}
              <div className="flex gap-2">
                {[10, 20, 40, 50, 100].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setTopNArtists(value)}
                    className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                      topNArtists === value
                        ? 'bg-blue-600 dark:bg-red-600 text-white'
                        : 'bg-slate-100 dark:bg-white/10 text-muted-foreground hover:bg-slate-200 dark:hover:bg-white/20'
                    }`}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>

            <p className="text-xs text-muted-foreground mt-2">
              {t('charts.storageWarning')}
            </p>
          </div>

          <div className="flex gap-3 pt-4">
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