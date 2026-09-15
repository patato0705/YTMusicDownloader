// src/pages/AdminPanel.tsx
import React, { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { Button } from '../components/ui/Button';
import { Spinner } from '../components/ui/Spinner';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import { Toast } from '../components/ui/Toast';
import { CreateUserModal } from '../components/ui/CreateUserModal';
import { SearchInput } from '../components/ui/SearchInput';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { Select } from '../components/ui/Select';
import { FollowChartModal } from '../components/ui/FollowChartModal';
import { ChartArtistGrid } from '../components/ui/ChartArtistGrid';
import { ToggleSwitch } from '../components/ui/ToggleSwitch';
import { InfoTooltip } from '../components/ui/InfoTooltip';
import * as adminApi from '../api/admin';
import * as chartsApi from '../api/charts';
import { cleanupLibrary } from '../api/library';
import { getFeatures } from '../api/features';
import type { CleanupResult } from '../api/library';
import type { Features } from '../api/features';
import { CHART_COUNTRIES, CHART_MAX_ARTISTS, getCountry } from '../config/charts';
import type { Setting, User } from '../api/admin';
import type { ChartSubscription, Chart } from '../api/charts';
import { parseApiError } from '../utils';

type Role = User['role'];

// Lowest to highest privilege
const ROLES: Role[] = ['visitor', 'member', 'administrator'];

const roleColors: Record<Role, string> = {
  administrator: 'bg-purple-500/20 text-purple-600 dark:text-purple-400',
  member: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
  visitor: 'bg-slate-500/20 text-slate-600 dark:text-slate-400',
};

// Every mutation on a chart subscription goes through a ConfirmDialog first.
type ChartAction =
  | { kind: 'unfollow'; sub: ChartSubscription }
  | { kind: 'toggle'; sub: ChartSubscription }
  | { kind: 'topN'; sub: ChartSubscription; value: number }
  | { kind: 'sync'; sub: ChartSubscription };

export default function AdminPanel(): JSX.Element {
  const [activeTab, setActiveTab] = useState<'users' | 'charts' | 'settings'>('users');
  const [settings, setSettings] = useState<Setting[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [editedSettings, setEditedSettings] = useState<Record<string, any>>({});
  
  // Toast notification
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  
  // Create user modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  
  // Delete confirmation
  const [deleteConfirm, setDeleteConfirm] = useState<{ userId: number; username: string } | null>(null);
  
  // Charts state
  const [chartSubscriptions, setChartSubscriptions] = useState<ChartSubscription[]>([]);
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
  
  // Cleanup
  const [cleanupLoading, setCleanupLoading] = useState(false);

  // Feature flags (drive which tabs are shown)
  const [features, setFeatures] = useState<Features | null>(null);

  // User filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [roleFilter, setRoleFilter] = useState<'all' | 'administrator' | 'member' | 'visitor'>('all');
  
  const { user } = useAuth();
  const { t, locale } = useI18n();

  // t() hands back the key itself when a translation is missing; settings are
  // defined on the backend, so fall back to the backend's English text.
  const tr = (key: string, fallback: string): string => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  // Localized language names for the ytmusic.language dropdown
  const languageNames = useMemo(() => {
    try {
      return new Intl.DisplayNames([locale], { type: 'language' });
    } catch {
      return null;
    }
  }, [locale]);

  // Role gating happens in <ProtectedRoute requiredRole="administrator">
  // around this route (see App.tsx) — a non-admin never mounts this component.

  const loadFeatures = async () => {
    try {
      setFeatures(await getFeatures());
    } catch (err) {
      console.error('Failed to load feature flags:', err);
    }
  };

  useEffect(() => { loadFeatures(); }, []);

  const chartsEnabled = features?.charts_enabled ?? true;

  // Don't leave the user on a tab that just got switched off
  useEffect(() => {
    if (activeTab === 'charts' && !chartsEnabled) setActiveTab('users');
  }, [activeTab, chartsEnabled]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setLoading(true);
      setError(null);

      try {
        if (activeTab === 'settings') {
          await loadSettings();
        } else if (activeTab === 'users') {
          await loadUsers();
        } else if (activeTab === 'charts') {
          await loadChartSubscriptions();
        }
      } catch (err: any) {
        console.error('Failed to load data:', err);
        if (!cancelled) setError(parseApiError(err, 'Failed to load data'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [activeTab]);

  const loadSettings = async () => {
    const settingsArray = await adminApi.getAllSettings();
    setSettings(settingsArray);

    // Initialize edited settings
    const initial: Record<string, any> = {};
    settingsArray.forEach(setting => {
      initial[setting.key] = setting.value;
    });
    setEditedSettings(initial);
  };

  const loadUsers = async () => {
    const usersData = await adminApi.listUsers(true); // Include inactive users
    setUsers(usersData);
  };

  const handleSettingChange = (key: string, value: any, type: string) => {
    let parsedValue = value;
    
    if (type === 'int') {
      // Keep an emptied field empty (rather than NaN) so it can be typed into;
      // saveSettings() refuses to submit it.
      parsedValue = value === '' ? '' : Number(value);
    } else if (type === 'bool') {
      parsedValue = value === 'true' || value === true;
    }
    
    setEditedSettings(prev => ({
      ...prev,
      [key]: parsedValue,
    }));
  };

  const settingLabel = (setting: Setting): string =>
    tr(
      `admin.settings.keys.${setting.key}.label`,
      setting.key.split('.').slice(1).join('.').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
    );

  const settingDescription = (setting: Setting): string =>
    tr(`admin.settings.keys.${setting.key}.description`, setting.description ?? '');

  const settingOptionLabel = (setting: Setting, option: adminApi.SettingOption): string => {
    const translated = t(`admin.settings.options.${setting.key}.${option.value}`);
    if (translated !== `admin.settings.options.${setting.key}.${option.value}`) return translated;
    if (setting.key === 'ytmusic.language' && languageNames) {
      try {
        const name = languageNames.of(option.value.replace('_', '-'));
        if (name) return name.charAt(0).toUpperCase() + name.slice(1);
      } catch {
        // unknown tag — use the backend label
      }
    }
    return option.label;
  };

  const invalidIntSetting = (setting: Setting): boolean => {
    if (setting.type !== 'int') return false;
    const value = editedSettings[setting.key];
    return !Number.isInteger(value) || (setting.min != null && value < setting.min);
  };

  const saveSettings = async () => {
    const invalid = settings.find(invalidIntSetting);
    if (invalid) {
      setToast({
        message: t('admin.settings.invalidNumber', { name: settingLabel(invalid), min: invalid.min ?? 0 }),
        type: 'error',
      });
      return;
    }

    setSaveLoading(true);
    setError(null);

    try {
      // Update each changed setting
      const updatePromises = Object.entries(editedSettings).map(([key, value]) => {
        const originalSetting = settings.find(s => s.key === key);
        if (originalSetting && originalSetting.value !== value) {
          return adminApi.updateSetting(key, value);
        }
        return Promise.resolve();
      });

      await Promise.all(updatePromises);
      
      await loadSettings();
      await loadFeatures();
      setToast({ message: t('admin.settings.saved'), type: 'success' });
    } catch (err: any) {
      setToast({ message: parseApiError(err, t('admin.settings.saveFailed')), type: 'error' });
    } finally {
      setSaveLoading(false);
    }
  };

  const toggleUserStatus = async (userId: number, currentStatus: boolean) => {
    try {
      if (currentStatus) {
        await adminApi.deactivateUser(userId);
      } else {
        await adminApi.activateUser(userId);
      }
      await loadUsers();
      setToast({ 
        message: currentStatus 
          ? t('admin.users.deactivated') 
          : t('admin.users.activated'), 
        type: 'success' 
      });
    } catch (err: any) {
      setToast({ message: parseApiError(err), type: 'error' });
    }
  };

  const changeUserRole = async (userId: number, newRole: string) => {
    try {
      await adminApi.updateUserRole(userId, newRole);
      await loadUsers();
      setToast({ message: t('admin.users.roleUpdated'), type: 'success' });
    } catch (err: any) {
      setToast({ message: parseApiError(err), type: 'error' });
    }
  };

  const deleteUser = async (userId: number, username: string) => {
    setDeleteConfirm({ userId, username });
  };

  const confirmDelete = async () => {
    if (!deleteConfirm) return;

    try {
      await adminApi.deleteUser(deleteConfirm.userId);
      await loadUsers();
      setToast({ message: t('admin.users.deleted'), type: 'success' });
    } catch (err: any) {
      setToast({ message: parseApiError(err), type: 'error' });
    } finally {
      setDeleteConfirm(null);
    }
  };

  // ============================================================================
  // CHARTS MANAGEMENT
  // ============================================================================

  const loadChartSubscriptions = async () => {
    const subs = await chartsApi.listChartSubscriptions(true);
    setChartSubscriptions(subs);
  };

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
      setToast({ message: parseApiError(err), type: 'error' });
      setSelectedChartData(null);
    } finally {
      setLoadingChart(false);
    }
  };

  const handleFollowChart = () => {
    if (!selectedCountry) return;
    setShowFollowModal(true);
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
      setToast({ message: parseApiError(err), type: 'error' });
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
      setToast({ message, type: 'success' });
      setChartAction(null);
    } catch (err: any) {
      setToast({ message: parseApiError(err), type: 'error' });
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

  // ============================================================================
  // LIBRARY CLEANUP
  // ============================================================================

  const handleCleanup = async () => {
    setCleanupLoading(true);
    try {
      const result: CleanupResult = await cleanupLibrary();
      const total = result.orphaned_tracks_removed + result.orphaned_albums_removed + result.orphaned_artists_removed;
      if (total === 0) {
        setToast({ message: t('admin.settings.cleanupNone'), type: 'success' });
      } else {
        const parts: string[] = [];
        if (result.orphaned_artists_removed > 0) parts.push(`${result.orphaned_artists_removed} artists`);
        if (result.orphaned_albums_removed > 0) parts.push(`${result.orphaned_albums_removed} albums`);
        if (result.orphaned_tracks_removed > 0) parts.push(`${result.orphaned_tracks_removed} tracks`);
        setToast({ message: `${t('admin.settings.cleanupDone')}: ${parts.join(', ')} removed`, type: 'success' });
      }
    } catch (err: any) {
      setToast({ message: parseApiError(err), type: 'error' });
    } finally {
      setCleanupLoading(false);
    }
  };

  // Filter users based on search and filters
  const filteredUsers = users.filter(u => {
    // Search filter
    const matchesSearch = searchQuery === '' || 
      u.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email.toLowerCase().includes(searchQuery.toLowerCase());
    
    // Status filter
    const matchesStatus = statusFilter === 'all' ||
      (statusFilter === 'active' && u.is_active) ||
      (statusFilter === 'inactive' && !u.is_active);
    
    // Role filter
    const matchesRole = roleFilter === 'all' || u.role === roleFilter;
    
    return matchesSearch && matchesStatus && matchesRole;
  });

  const renderSettingsTab = () => {
    // Group settings by category
    const grouped: Record<string, Setting[]> = {};
    settings.forEach(setting => {
      const category = setting.key.split('.')[0];
      if (!grouped[category]) grouped[category] = [];
      grouped[category].push(setting);
    });

    return (
      <div className="space-y-8">
        {Object.entries(grouped).map(([category, categorySettings]) => (
          <section key={category}>
            <SectionHeader>
              {tr(`admin.settings.categories.${category}`, category.charAt(0).toUpperCase() + category.slice(1))}
            </SectionHeader>
            
            <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10 space-y-4">
              {categorySettings.map(setting => (
                <div key={setting.key} className="flex items-center justify-between py-3 border-b border-slate-200 dark:border-white/10 last:border-0">
                  <div className="flex-1 mr-4">
                    <label className="font-semibold text-foreground block mb-1">
                      {settingLabel(setting)}
                    </label>
                    <p className="text-sm text-muted-foreground">{settingDescription(setting)}</p>
                  </div>
                  
                  <div className="flex-shrink-0">
                    {setting.type === 'bool' ? (
                      <ToggleSwitch
                        checked={!!editedSettings[setting.key]}
                        onChange={(checked) => handleSettingChange(setting.key, checked, setting.type)}
                      />
                    ) : setting.type === 'int' ? (
                      <input
                        type="number"
                        min={setting.min ?? undefined}
                        step={1}
                        value={editedSettings[setting.key] ?? ''}
                        onChange={(e) => handleSettingChange(setting.key, e.target.value, setting.type)}
                        className={`w-24 px-3 py-2 glass rounded-xl text-foreground text-center focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 ${
                          invalidIntSetting(setting)
                            ? 'border border-red-500 dark:border-red-500'
                            : 'border-slate-200 dark:border-white/10'
                        }`}
                      />
                    ) : Array.isArray(setting.allowed_values) && setting.allowed_values.length > 0 ? (
                      <Select
                        value={editedSettings[setting.key] ?? ''}
                        onChange={(value) => handleSettingChange(setting.key, value, setting.type)}
                        options={setting.allowed_values.map(option => ({
                          value: option.value,
                          label: settingOptionLabel(setting, option),
                        }))}
                        className="w-48"
                      />
                    ) : (
                      <input
                        type="text"
                        value={editedSettings[setting.key] ?? ''}
                        onChange={(e) => handleSettingChange(setting.key, e.target.value, setting.type)}
                        className="w-48 px-3 py-2 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600"
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}

        <div className="flex justify-end">
          <Button
            onClick={saveSettings}
            isLoading={saveLoading}
            variant="primary"
            size="lg"
          >
            {t('admin.settings.save')}
          </Button>
        </div>

        {/* Maintenance */}
        <section>
          <SectionHeader>{t('admin.settings.maintenance')}</SectionHeader>

          <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10 space-y-4">
            <div className="flex items-center justify-between py-3">
              <div className="flex-1 mr-4">
                <label className="font-semibold text-foreground block mb-1">
                  {t('admin.settings.cleanupTitle')}
                </label>
                <p className="text-sm text-muted-foreground">
                  {t('admin.settings.cleanupDescription')}
                </p>
              </div>
              <div className="flex-shrink-0">
                <Button
                  onClick={handleCleanup}
                  isLoading={cleanupLoading}
                  variant="outline"
                >
                  {t('admin.settings.cleanupButton')}
                </Button>
              </div>
            </div>
          </div>
        </section>
      </div>
    );
  };

  const renderChartsTab = () => {
    const followedCountryCodes = new Set(chartSubscriptions.map(s => s.country_code));
    const availableCountries = CHART_COUNTRIES.filter(c => !followedCountryCodes.has(c.code));
    const thClass = 'px-6 py-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider';

    return (
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
                onClick={handleFollowChart}
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
    );
  };

  const renderUsersTab = () => {
    const roleOptions = ROLES.map(role => ({ value: role, label: t(`admin.users.roles.${role}`) }));

    // Shown in the info bubble next to the "Role" column header
    const roleInfo = (
      <div className="space-y-3">
        {ROLES.map(role => (
          <div key={role}>
            <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold mb-1 ${roleColors[role]}`}>
              {t(`admin.users.roles.${role}`)}
            </span>
            <p className="text-xs leading-snug text-muted-foreground">{t(`admin.users.roleInfo.${role}`)}</p>
          </div>
        ))}
      </div>
    );

    return (
      <div className="space-y-6">
        {/* Search and Filters */}
        <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10 space-y-4">
          <div className="flex flex-col md:flex-row gap-4">
            {/* Search */}
            <div className="flex-1">
              <SearchInput
                value={searchQuery}
                onChange={setSearchQuery}
                placeholder={t('admin.users.search')}
                showClearButton
                onClear={() => setSearchQuery('')}
              />
            </div>

            {/* Status Filter */}
            <Select
              value={statusFilter}
              onChange={(value) => setStatusFilter(value as any)}
              options={[
                { value: 'all', label: t('admin.users.allStatuses') },
                { value: 'active', label: t('admin.users.active') },
                { value: 'inactive', label: t('admin.users.inactive') },
              ]}
            />

            {/* Role Filter */}
            <Select
              value={roleFilter}
              onChange={(value) => setRoleFilter(value as any)}
              options={[
                { value: 'all', label: t('admin.users.allRoles') },
                ...roleOptions,
              ]}
            />

            {/* Create User Button */}
            <Button
              onClick={() => setShowCreateModal(true)}
              variant="primary"
            >
              + {t('admin.users.create')}
            </Button>
          </div>

          {/* Results count */}
          <div className="text-sm text-muted-foreground">
            {t('admin.users.showing')} {filteredUsers.length} {t('admin.users.of')} {users.length} {t('admin.users.users')}
          </div>
        </div>

        {/* Users Table */}
        <div className="glass rounded-2xl overflow-hidden border border-slate-200/50 dark:border-white/10">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-100/50 dark:bg-white/5 border-b border-slate-200 dark:border-white/10">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {t('admin.users.username')}
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {t('admin.users.email')}
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    <span className="inline-flex items-center gap-1.5">
                      {t('admin.users.role')}
                      <InfoTooltip label={t('admin.users.roleInfo.title')} content={roleInfo} />
                    </span>
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {t('admin.users.status')}
                  </th>
                  <th className="px-6 py-4 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {t('admin.users.actions')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-white/10">
                {filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center">
                      <div className="text-muted-foreground">
                        <span className="text-4xl mb-2 block">👥</span>
                        <p>{t('admin.users.noResults')}</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-semibold text-foreground">{u.username}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm text-muted-foreground">{u.email}</div>
                      </td>
                      <td className="px-6 py-4">
                        <Select
                          value={u.role}
                          onChange={(value) => changeUserRole(u.id, value)}
                          options={roleOptions}
                          disabled={u.id === user?.id}
                          className={`text-xs font-medium ${roleColors[u.role]} border-0 py-1`}
                        />
                      </td>
                      <td className="px-6 py-4">
                        <ToggleSwitch
                          checked={u.is_active}
                          onChange={() => toggleUserStatus(u.id, u.is_active)}
                          disabled={u.id === user?.id}
                          label={u.is_active ? t('admin.users.active') : t('admin.users.inactive')}
                        />
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Button
                          onClick={() => deleteUser(u.id, u.username)}
                          variant="danger"
                          size="sm"
                          disabled={u.id === user?.id}
                        >
                          {t('admin.users.delete')}
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  };

  if (loading && settings.length === 0 && users.length === 0) {
    return (
      <div className="relative min-h-screen">
        <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        <div className="relative z-10 flex items-center justify-center py-20">
          <div className="text-center">
            <Spinner size="lg" className="mx-auto mb-4 text-blue-600 dark:text-red-500" />
            <p className="text-muted-foreground">{t('common.loading')}</p>
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
      
      {/* Toast notification */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}

      {/* Create User Modal */}
      {showCreateModal && (
        <CreateUserModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            loadUsers();
            setToast({ message: t('admin.users.created'), type: 'success' });
          }}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        title={t('admin.users.deleteTitle')}
        message={
          deleteConfirm
            ? t('admin.users.confirmDelete', { username: deleteConfirm.username })
            : ''
        }
        confirmText={t('admin.users.delete')}
        cancelText={t('common.cancel')}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirm(null)}
        variant="danger"
      />

      {/* Chart action confirmation */}
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

      {/* Follow Chart Modal */}
      {showFollowModal && selectedCountry && (
        <FollowChartModal
          country={getCountry(selectedCountry)!}
          onClose={() => setShowFollowModal(false)}
          onSuccess={async () => {
            await loadChartSubscriptions();
            setToast({ message: t('admin.charts.followed'), type: 'success' });
            setSelectedCountry('');
            setSelectedChartData(null);
          }}
        />
      )}
      
      {/* Main content */}
      <div className="relative z-10 space-y-8 pb-12">
        {/* Page header */}
        <PageHero
          title={
            <>
              <span className="text-foreground">{t('admin.title')} </span>
              <span className="text-gradient">{t('admin.panel')}</span>
            </>
          }
          subtitle={t('admin.subtitle')}
        />

        {/* Error message */}
        {error && (
          <div className="bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl p-4 border border-red-500/20">
            <div className="flex items-center gap-3">
              <span className="text-xl">⚠️</span>
              <p className="text-sm text-red-600 dark:text-red-400 font-medium">{error}</p>
            </div>
          </div>
        )}

        {/* Tab navigation */}
        <div className="flex items-center gap-2 glass rounded-2xl p-2 w-fit">
          <button
            onClick={() => setActiveTab('users')}
            className={`px-6 py-3 rounded-xl font-medium transition-all duration-300 ${
              activeTab === 'users'
                ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
            }`}
          >
            👥 {t('admin.tabs.users')}
          </button>
          {chartsEnabled && (
            <button
              onClick={() => setActiveTab('charts')}
              className={`px-6 py-3 rounded-xl font-medium transition-all duration-300 ${
                activeTab === 'charts'
                  ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                  : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
              }`}
            >
              📊 {t('admin.tabs.charts')}
            </button>
          )}
          <button
            onClick={() => setActiveTab('settings')}
            className={`px-6 py-3 rounded-xl font-medium transition-all duration-300 ${
              activeTab === 'settings'
                ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
            }`}
          >
            ⚙️ {t('admin.tabs.settings')}
          </button>
        </div>

        {/* Tab content */}
        {activeTab === 'users' ? renderUsersTab() 
          : activeTab === 'charts' ? renderChartsTab()
          : renderSettingsTab()}
      </div>
    </div>
  );
}