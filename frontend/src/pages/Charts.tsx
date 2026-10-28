// src/pages/Charts.tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { useAuth } from '../contexts/AuthContext';
import { PageHeader } from '../components/ui/PageHeader';
import { buttonClass } from '../components/ui/Button';
import { ChartArtistGrid } from '../components/ui/ChartArtistGrid';
import { EmptyState, ErrorBanner, LoadingState } from '../components/ui/PageStatus';
import * as chartsApi from '../api/charts';
import type { ChartSubscription, Chart } from '../api/charts';
import { getCountry, useCountryName } from '../config/charts';
import { apiErrorMessage } from '../utils';

export default function Charts(): JSX.Element {
  const { user } = useAuth();
  const isAdmin = user?.role === 'administrator';
  const [subscriptions, setSubscriptions] = useState<ChartSubscription[]>([]);
  const [charts, setCharts] = useState<Record<string, Chart>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { t, formatLocale } = useI18n();
  const countryName = useCountryName();

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const subs = await chartsApi.listChartSubscriptions();
        // A chart that fails to load is left out, not the whole page
        const loaded = await Promise.all(subs.map(async (sub) => {
          try {
            return [sub.country_code, await chartsApi.getChart(sub.country_code)] as const;
          } catch (err) {
            console.error(`Failed to load chart for ${sub.country_code}:`, err);
            return null;
          }
        }));
        if (cancelled) return;
        setSubscriptions(subs);
        setCharts(Object.fromEntries(loaded.filter((entry) => entry !== null)));
      } catch (err: any) {
        console.error('Failed to load charts:', err);
        if (!cancelled) {
          setError(err?.status === 403 ? t('charts.disabled') : apiErrorMessage(err, t, t('common.error')));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, []);

  const content = () => {
    if (loading) return <LoadingState className="py-8" />;
    if (error) return <ErrorBanner title={t('charts.errorTitle')}>{error}</ErrorBanner>;
    if (subscriptions.length === 0) {
      return (
        // Admins can fix it themselves, so they get the way there instead of "contact an administrator"
        <EmptyState icon="chart" title={t('charts.noCharts')}>
          {isAdmin ? (
            <>
              <p>{t('charts.noChartsAdminDescription')}</p>
              <Link
                to="/admin?tab=charts"
                className={buttonClass('primary', 'lg')}
              >
                {t('admin.charts.followChart')}
              </Link>
            </>
          ) : (
            <p>{t('charts.noChartsDescription')}</p>
          )}
        </EmptyState>
      );
    }

    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {subscriptions.map((subscription) => {
          const country = getCountry(subscription.country_code);
          const chart = charts[subscription.country_code];
          if (!chart || !country) return null;

          return (
            <div key={subscription.country_code} className="glass rounded-3xl p-6 border-gradient">
              <div className="flex items-center gap-3 mb-4">
                <span className="text-4xl" aria-hidden="true">{country.flag}</span>
                <div>
                  <h3 className="text-xl font-bold text-foreground">{countryName(country.code)}</h3>
                  <p className="text-sm text-muted-foreground">
                    {t('charts.followingTopN', { n: subscription.top_n_artists, total: chart.artists.length })}
                  </p>
                </div>
              </div>

              <ChartArtistGrid artists={chart.artists} maxHeight="280px" />

              {subscription.last_synced_at && (
                <p className="text-xs text-muted-foreground mt-4 text-center">
                  {t('charts.lastUpdated', { date: new Date(subscription.last_synced_at).toLocaleString(formatLocale) })}
                </p>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="space-y-8 pb-12">
      <PageHeader icon="chart" title={t('nav.charts')} subtitle={t('charts.heroSubtitle')} />
      {content()}
    </div>
  );
}
