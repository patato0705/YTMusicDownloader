// src/pages/Charts.tsx
import React, { useEffect, useState } from 'react';
import { useI18n } from '../contexts/I18nContext';
import { PageHero } from '../components/ui/PageHero';
import { Spinner } from '../components/ui/Spinner';
import { ChartArtistGrid } from '../components/ui/ChartArtistGrid';
import * as chartsApi from '../api/charts';
import { getCountry } from '../config/charts';
import type { ChartSubscription, Chart } from '../api/charts';

export default function Charts(): JSX.Element {
  const [subscriptions, setSubscriptions] = useState<ChartSubscription[]>([]);
  const [charts, setCharts] = useState<Record<string, Chart>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { t } = useI18n();

  useEffect(() => {
    loadCharts();
  }, []);

  const loadCharts = async () => {
    setLoading(true);
    setError(null);

    try {
      // Load all enabled subscriptions
      const subs = await chartsApi.listChartSubscriptions(false);
      setSubscriptions(subs.filter(s => s.enabled));

      // Load chart data for each subscription
      const chartData: Record<string, Chart> = {};
      await Promise.all(
        subs
          .filter(s => s.enabled)
          .map(async (sub) => {
            try {
              const chart = await chartsApi.getChart(sub.country_code);
              chartData[sub.country_code] = chart;
            } catch (err) {
              console.error(`Failed to load chart for ${sub.country_code}:`, err);
            }
          })
      );

      setCharts(chartData);
    } catch (err: any) {
      console.error('Failed to load charts:', err);
      setError(err.message || 'Failed to load charts');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="relative min-h-screen">
        <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        <div className="relative z-10 space-y-8 pb-12">
          <PageHero
            title={
              <>
                <span className="text-foreground">Music </span>
                <span className="text-gradient">Charts</span>
              </>
            }
            subtitle={t('charts.heroSubtitle')}
          />
          
          <div className="relative z-10 text-center">
            <Spinner size="lg" className="mx-auto mb-4 text-blue-600 dark:text-red-500"/>
            <p className="text-muted-foreground">{t('common.loading')}</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="relative min-h-screen">
        <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        <div className="relative z-10 space-y-8 pb-12">
          <PageHero
            title={
              <>
                <span className="text-foreground">Music </span>
                <span className="text-gradient">Charts</span>
              </>
            }
            subtitle={t('charts.heroSubtitle')}
          />
          
          <div className="bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl p-6 border border-red-500/20">
            <div className="flex items-center gap-3">
              <span className="text-2xl">⚠️</span>
              <div>
                <h3 className="font-semibold text-red-600 dark:text-red-400 mb-1">
                  {t('charts.errorTitle')}
                </h3>
                <p className="text-sm text-red-600/80 dark:text-red-400/80">{error}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (subscriptions.length === 0) {
    return (
      <div className="relative min-h-screen">
        <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        <div className="relative z-10 space-y-8 pb-12">
          <PageHero
            title={
              <>
                <span className="text-foreground">Music </span>
                <span className="text-gradient">Charts</span>
              </>
            }
            subtitle={t('charts.heroSubtitle')}
          />
          
          <div className="bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-16 border border-slate-200/50 dark:border-white/10 text-center">
            <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-6">
              <span className="text-5xl">📊</span>
            </div>
            <h3 className="text-2xl font-bold mb-3 text-foreground">{t('charts.noCharts')}</h3>
            <p className="text-muted-foreground max-w-md mx-auto">
              {t('charts.noChartsDescription')}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen">
      {/* Background effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
      
      {/* Main content */}
      <div className="relative z-10 space-y-8 pb-12">
        <PageHero
          title={
            <>
              <span className="text-foreground">{t('charts.music')} </span>
              <span className="text-gradient">{t('nav.charts')}</span>
            </>
          }
          subtitle="Discover trending artists from around the world"
        />

        {/* Chart Cards Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {subscriptions.map((subscription) => {
            const country = getCountry(subscription.country_code);
            const chart = charts[subscription.country_code];

            if (!chart || !country) return null;

            // Limit to top_n_artists
            const displayedArtists = chart.artists.slice(0, subscription.top_n_artists);

            return (
              <div 
                key={subscription.country_code}
                className="dark:glass glass rounded-3xl p-6 border-gradient"
              >
                {/* Country Header */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span className="text-4xl">{country.flag}</span>
                    <div>
                      <h3 className="text-xl font-bold text-foreground">
                        {country.name}
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        {t('charts.topNArtists', { n: subscription.top_n_artists })}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Artists Grid */}
                <ChartArtistGrid 
                  artists={displayedArtists} 
                  maxHeight="280px"
                />

                {/* Last sync info */}
                {subscription.last_synced_at && (
                  <p className="text-xs text-muted-foreground mt-4 text-center">
                    {t('charts.lastUpdated', { date: new Date(subscription.last_synced_at).toLocaleString() })}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}