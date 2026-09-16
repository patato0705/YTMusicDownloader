// src/components/admin/ChartsTab.tsx
/**
 * Admin panel > Charts: follow a country chart, manage existing subscriptions
 * (top-N, enable/disable, sync, unfollow). Every mutation goes through a
 * ConfirmDialog first.
 */
import React, { useEffect, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../ui/Button';
import { Spinner } from '../ui/Spinner';
import { SectionHeader } from '../ui/SectionHeader';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { Select } from '../ui/Select';
import { FollowChartModal } from '../ui/FollowChartModal';
import { ChartArtistGrid } from '../ui/ChartArtistGrid';
import { ToggleSwitch } from '../ui/ToggleSwitch';
import * as chartsApi from '../../api/charts';
import type { ChartSubscription, Chart } from '../../api/charts';
import { CHART_COUNTRIES, CHART_MAX_ARTISTS, getCountry } from '../../config/charts';
import { parseApiError } from '../../utils';
import { AdminTabShell } from './AdminTabShell';
import type { AdminTabProps } from './AdminTabShell';

type ChartAction =
  | { kind: 'unfollow'; sub: ChartSubscription }
  | { kind: 'toggle'; sub: ChartSubscription }
  | { kind: 'topN'; sub: ChartSubscription; value: number }
  | { kind: 'sync'; sub: ChartSubscription };

export const ChartsTab: React.FC<AdminTabProps> = ({ onToast }) => {
  const { t, locale } = useI18n();

  const [chartSubscriptions, setChartSubscriptions] = useState<ChartSubscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedCountry, setSelectedCountry] = useState<string>('');
  const [selectedChartData, setSelectedChartData] = useState<Chart | null>(null);
  const [showFollowModal, setShowFollowModal] = useState(false);
  const [loadingChart, setLoadingChart] = useState(false);
  const [chartAction, setChartAction] = useState<ChartAction | null>(null);
  const [chartActionLoading, setChartActionLoading] = useState(false);
  // Top-N edits are staged per country and only sent once confirmed
  const [topNDrafts, setTopNDrafts] = useState<Record<string, string>>({});
  // Full chart expanded under a subscription row (the top selector only lists unfollowed countries)
  const [expandedChart, setExpandedChart] = useState<{ code: string; chart: Chart | null; loading: boolean } | null>(null);

  const loadChartSubscriptions = async () => {
    const subs = await chartsApi.listChartSubscriptions(true);
    setChartSubscriptions(subs);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        await loadChartSubscriptions();
      } catch (err: any) {
        console.error('Failed to load chart subscriptions:', err);
        if (!cancelled) setError(parseApiError(err, 'Failed to load data'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleCountrySelect = async (countryCode: string) => {
    setSelectedCountry(countryCode);
    if (!countryCode) {
      setSelectedChartData(null);
      return;
    }

    setLoadingChart(true);
    try {
      const chart = await chartsApi.getChart(countryCode);
      setSelectedChartData(chart);
    } catch (err: any) {
      console.error('Failed to load chart:', err);
      onToast(parseApiError(err), 'error');
      setSelectedChartData(null);
    } finally {
      setLoadingChart(false);
    }
  };

  const togglePreview = async (sub: ChartSubscription) => {
    const code = sub.country_code;
    if (expandedChart?.code === code) {
      setExpandedChart(null);
      return;
    }

    setExpandedChart({ code, chart: null, loading: true });
    try {
      const chart = await chartsApi.getChart(code);
      setExpandedChart(prev => (prev?.code === code ? { code, chart, loading: false } : prev));
    } catch (err: any) {
      onToast(parseApiError(err), 'error');
      setExpandedChart(prev => (prev?.code === code ? null : prev));
    }
  };

  const countryName = (sub: ChartSubscription): string =>
    getCountry(sub.country_code)?.name ?? sub.country_code;

  const topNDraft = (sub: ChartSubscription): string =>
    topNDrafts[sub.country_code] ?? String(sub.top_n_artists);

  const setTopNDraft = (countryCode: string, value: string) =>
    setTopNDrafts(prev => ({ ...prev, [countryCode]: value }));

  const clearTopNDraft = (countryCode: string) =>
    setTopNDrafts(prev => {
      const { [countryCode]: _removed, ...rest } = prev;
      return rest;
    });

  const parseTopN = (text: string): number | null => {
    const n = Number(text);
    return Number.isInteger(n) && n >= 1 && n <= CHART_MAX_ARTISTS ? n : null;
  };

  const requestTopNChange = (sub: ChartSubscription) => {
    const value = parseTopN(topNDraft(sub));
    if (value === null) return;
    if (value === sub.top_n_artists) {
      clearTopNDraft(sub.country_code);
      return;
    }
    setChartAction({ kind: 'topN', sub, value });
  };

  const runChartAction = async () => {
    if (!chartAction) return;
    const { sub } = chartAction;
    const code = sub.country_code;

    setChartActionLoading(true);
    try {
      let message: string;
      switch (chartAction.kind) {
        case 'unfollow':
          await chartsApi.unfollowChart(code);
          message = t('admin.charts.unfollowed');
          // Clear selection if we unfollowed the currently selected chart
          if (code === selectedCountry) {
            setSelectedCountry('');
            setSelectedChartData(null);
          }
          break;
        case 'toggle':
          await chartsApi.updateChart(code, { enabled: !sub.enabled });
          message = sub.enabled ? t('admin.charts.disabledToast') : t('admin.charts.enabledToast');
          break;
        case 'topN':
          await chartsApi.updateChart(code, { top_n_artists: chartAction.value });
          clearTopNDraft(code);
          message = t('admin.charts.updated');
          break;
        case 'sync':
          await chartsApi.syncChart(code);
          message = t('admin.charts.syncQueued');
          break;
      }
      await loadChartSubscriptions();
      onToast(message, 'success');
      setChartAction(null);
    } catch (err: any) {
      onToast(parseApiError(err), 'error');
    } finally {
      setChartActionLoading(false);
    }
  };

  // Copy for the confirmation dialog of the pending chart action
  const chartActionDialog = (action: ChartAction) => {
    const country = countryName(action.sub);
    switch (action.kind) {
      case 'unfollow':
        return {
          title: t('admin.charts.confirm.unfollowTitle'),
          message: t('admin.charts.confirm.unfollow', { country }),
          confirmText: t('admin.charts.unfollowChart'),
          variant: 'danger' as const,
        };
      case 'toggle':
        return action.sub.enabled
          ? {
              title: t('admin.charts.confirm.disableTitle'),
              message: t('admin.charts.confirm.disable', { country }),
              confirmText: t('admin.charts.disable'),
              variant: 'warning' as const,
            }
          : {
              title: t('admin.charts.confirm.enableTitle'),
              message: t('admin.charts.confirm.enable', { country }),
              confirmText: t('admin.charts.enable'),
              variant: 'info' as const,
            };
      case 'topN': {
        const increasing = action.value > action.sub.top_n_artists;
        return {
          title: t('admin.charts.confirm.topNTitle'),
          message: t(
            increasing ? 'admin.charts.confirm.topNIncrease' : 'admin.charts.confirm.topNDecrease',
            { country, from: action.sub.top_n_artists, to: action.value },
          ),
          confirmText: t('admin.charts.apply'),
          variant: increasing ? ('warning' as const) : ('info' as const),
        };
      }
      case 'sync':
        return {
          title: t('admin.charts.confirm.syncTitle'),
          message: t('admin.charts.confirm.sync', { country, n: action.sub.top_n_artists }),
          confirmText: t('admin.charts.syncNow'),
          variant: 'info' as const,
        };
    }
  };

  const followedCountryCodes = new Set(chartSubscriptions.map(s => s.country_code));
  const availableCountries = CHART_COUNTRIES.filter(c => !followedCountryCodes.has(c.code));
  const thClass = 'px-6 py-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider';

  return (
    <AdminTabShell loading={loading} error={error}>
      {chartAction && (() => {
        const dialog = chartActionDialog(chartAction);
        return (
          <ConfirmDialog
            isOpen
            title={dialog.title}
            message={dialog.message}
            confirmText={dialog.confirmText}
            cancelText={t('common.cancel')}
            variant={dialog.variant}
            isLoading={chartActionLoading}
            onConfirm={runChartAction}
            onCancel={() => { if (!chartActionLoading) setChartAction(null); }}
          />
        );
      })()}

      {showFollowModal && selectedCountry && (
        <FollowChartModal
          country={getCountry(selectedCountry)!}
          onClose={() => setShowFollowModal(false)}
          onSuccess={async () => {
            await loadChartSubscriptions();
            onToast(t('admin.charts.followed'), 'success');
            setSelectedCountry('');
            setSelectedChartData(null);
          }}
        />
      )}

      <div className="space-y-8">
        {/* Follow a new chart */}
        <section>
          <SectionHeader>{t('admin.charts.followChart')}</SectionHeader>

          <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10">
            <div className="flex flex-col md:flex-row gap-4">
              <div className="flex-1">
                <Select
                  value={selectedCountry}
                  onChange={handleCountrySelect}
                  options={[
                    { value: '', label: t('admin.charts.selectCountry') },
                    ...availableCountries.map(c => ({
                      value: c.code,
                      label: `${c.flag} ${c.name}`
                    }))
                  ]}
                  className="w-full"
                />
              </div>

              <Button
                onClick={() => { if (selectedCountry) setShowFollowModal(true); }}
                variant="primary"
                disabled={!selectedCountry || loadingChart}
              >
                + {t('admin.charts.followChart')}
              </Button>
            </div>

            {/* Chart Preview */}
            {loadingChart && (
              <div className="mt-4 flex items-center justify-center py-8">
                <Spinner />
              </div>
            )}

            {selectedChartData && !loadingChart && (
              <div className="mt-4 glass rounded-xl p-4 border border-slate-200/50 dark:border-white/10">
                <div className="flex items-center gap-3 mb-4">
                  <span className="text-3xl">{getCountry(selectedCountry)?.flag}</span>
                  <div>
                    <h4 className="font-semibold text-foreground">{getCountry(selectedCountry)?.name}</h4>
                    <p className="text-sm text-muted-foreground">
                      {t('admin.charts.previewTop', { n: CHART_MAX_ARTISTS })}
                    </p>
                  </div>
                </div>

                <ChartArtistGrid
                  artists={selectedChartData.artists.slice(0, CHART_MAX_ARTISTS)}
                  maxHeight="200px"
                />
              </div>
            )}
          </div>
        </section>

        {/* Current Subscriptions */}
        <section>
          <SectionHeader>{t('admin.charts.currentSubscriptions')}</SectionHeader>

          <div className="glass rounded-2xl overflow-hidden border border-slate-200/50 dark:border-white/10">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-100/50 dark:bg-white/5 border-b border-slate-200 dark:border-white/10">
                  <tr>
                    <th className={`${thClass} text-left`}>{t('admin.charts.country')}</th>
                    <th className={`${thClass} text-left`}>{t('admin.charts.topArtists')}</th>
                    <th className={`${thClass} text-left`}>{t('admin.charts.status')}</th>
                    <th className={`${thClass} text-left`}>{t('admin.charts.lastSynced')}</th>
                    <th className={`${thClass} text-right`}>{t('admin.charts.actions')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-white/10">
                  {chartSubscriptions.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center">
                        <div className="text-muted-foreground">
                          <span className="text-4xl mb-2 block">📊</span>
                          <p>{t('admin.charts.noSubscriptions')}</p>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    chartSubscriptions.map((sub) => {
                      const country = getCountry(sub.country_code);
                      const draft = topNDraft(sub);
                      const draftValue = parseTopN(draft);
                      const draftDirty = draft !== String(sub.top_n_artists);
                      const busy = chartActionLoading && chartAction?.sub.country_code === sub.country_code;
                      const expanded = expandedChart?.code === sub.country_code ? expandedChart : null;

                      return (
                        <React.Fragment key={sub.id}>
                        <tr className="hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <span className="text-2xl">{country?.flag ?? '🌐'}</span>
                              <span className="font-semibold text-foreground">{country?.name ?? sub.country_code}</span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              <input
                                type="number"
                                min={1}
                                max={CHART_MAX_ARTISTS}
                                step={1}
                                value={draft}
                                disabled={busy}
                                onChange={(e) => setTopNDraft(sub.country_code, e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') requestTopNChange(sub);
                                  if (e.key === 'Escape') clearTopNDraft(sub.country_code);
                                }}
                                className={`w-20 px-3 py-2 glass rounded-xl text-foreground text-center focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 disabled:opacity-50 ${
                                  draftValue === null
                                    ? 'border border-red-500 dark:border-red-500'
                                    : 'border-slate-200 dark:border-white/10'
                                }`}
                              />
                              {draftDirty && (
                                <>
                                  <Button
                                    onClick={() => requestTopNChange(sub)}
                                    variant="outline"
                                    size="sm"
                                    disabled={draftValue === null || busy}
                                  >
                                    {t('admin.charts.apply')}
                                  </Button>
                                  <Button
                                    onClick={() => clearTopNDraft(sub.country_code)}
                                    variant="ghost"
                                    size="sm"
                                    disabled={busy}
                                  >
                                    {t('common.cancel')}
                                  </Button>
                                </>
                              )}
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <ToggleSwitch
                              checked={sub.enabled}
                              onChange={() => setChartAction({ kind: 'toggle', sub })}
                              disabled={busy}
                              label={sub.enabled ? t('admin.charts.enabled') : t('admin.charts.disabled')}
                            />
                          </td>
                          <td className="px-6 py-4">
                            <div className="text-sm text-muted-foreground">
                              {sub.last_synced_at
                                ? new Date(sub.last_synced_at).toLocaleString(locale)
                                : t('admin.charts.neverSynced')}
                            </div>
                            {sub.last_error && (
                              <div
                                className="mt-1 text-xs text-red-600 dark:text-red-400 max-w-xs truncate"
                                title={sub.last_error}
                              >
                                ⚠️ {sub.last_error}
                              </div>
                            )}
                          </td>
                          <td className="px-6 py-4 text-right">
                            <div className="inline-flex items-center gap-2">
                              <Button
                                onClick={() => togglePreview(sub)}
                                variant="ghost"
                                size="sm"
                                isLoading={!!expanded?.loading}
                              >
                                {expanded ? t('admin.charts.hidePreview') : t('admin.charts.preview')}
                              </Button>
                              <Button
                                onClick={() => setChartAction({ kind: 'sync', sub })}
                                variant="outline"
                                size="sm"
                                disabled={!sub.enabled || busy}
                                title={!sub.enabled ? t('admin.charts.syncDisabledHint') : undefined}
                              >
                                {t('admin.charts.syncNow')}
                              </Button>
                              <Button
                                onClick={() => setChartAction({ kind: 'unfollow', sub })}
                                variant="danger"
                                size="sm"
                                disabled={busy}
                              >
                                {t('admin.charts.unfollowChart')}
                              </Button>
                            </div>
                          </td>
                        </tr>
                        {expanded?.chart && (
                          <tr className="bg-slate-50/60 dark:bg-white/[0.03]">
                            <td colSpan={5} className="px-6 py-4">
                              <p className="text-sm text-muted-foreground mb-3">
                                {t('admin.charts.previewFollowing', {
                                  n: sub.top_n_artists,
                                  total: expanded.chart.artists.length,
                                })}
                              </p>
                              <ChartArtistGrid artists={expanded.chart.artists} maxHeight="280px" />
                            </td>
                          </tr>
                        )}
                        </React.Fragment>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </AdminTabShell>
  );
};
