// src/pages/admin/AdminPanel.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
import * as adminApi from '../api/admin';
import * as chartsApi from '../api/charts';
import { cleanupLibrary } from '../api/library';
import type { CleanupResult } from '../api/library';
import { CHART_COUNTRIES, getCountry } from '../config/charts';
import type { Setting, User } from '../api/admin';
import type { ChartSubscription, Chart } from '../api/charts';

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
  
  // Cleanup
  const [cleanupLoading, setCleanupLoading] = useState(false);

  // User filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [roleFilter, setRoleFilter] = useState<'all' | 'administrator' | 'member' | 'visitor'>('all');
  
  const { user } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

  // Redirect if not admin
  useEffect(() => {
    if (user && user.role !== 'administrator') {
      navigate('/');
    }
  }, [user, navigate]);

  useEffect(() => {
    loadData();
  }, [activeTab]);

  const loadData = async () => {
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
      setError(err.message || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const loadSettings = async () => {
    const settingsArray = await adminApi.getAllSettings();
    console.log('[AdminPanel] settings response:', settingsArray);
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
      parsedValue = parseInt(value, 10);
    } else if (type === 'bool') {
      parsedValue = value === 'true' || value === true;
    }
    
    setEditedSettings(prev => ({
      ...prev,
      [key]: parsedValue,
    }));
  };

  const saveSettings = async () => {
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
      setToast({ message: t('admin.settings.saved') || 'Settings saved successfully', type: 'success' });
    } catch (err: any) {
      setToast({ message: err.message || 'Failed to save settings', type: 'error' });
    } finally {
      setSaveLoading(false);
    }
  };

  // Parse API errors from ApiError class (err.data holds the raw response body)
  const parseApiError = (err: any): string => {
    const data = err.data;

    if (data?.detail && Array.isArray(data.detail)) {
      return data.detail.map((e: any) => {
        const field = e.loc && e.loc.length > 1 ? e.loc[e.loc.length - 1] : null;
        const msg = e.msg || 'Invalid value';
        return field ? `${field}: ${msg}` : msg;
      }).join(', ');
    }

    if (data?.detail && typeof data.detail === 'string') {
      return data.detail;
    }

    return err.message || 'An error occurred';
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
          ? (t('admin.users.deactivated') || 'User deactivated') 
          : (t('admin.users.activated') || 'User activated'), 
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
      setToast({ message: t('admin.users.roleUpdated') || 'Role updated successfully', type: 'success' });
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
      setToast({ message: t('admin.users.deleted') || 'User deleted successfully', type: 'success' });
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

  const handleUnfollowChart = async (countryCode: string) => {
    try {
      await chartsApi.unfollowChart(countryCode);
      await loadChartSubscriptions();
      setToast({ message: t('admin.charts.unfollowed') || 'Chart unfollowed successfully', type: 'success' });
      
      // Clear selection if we unfollowed the currently selected chart
      if (countryCode === selectedCountry) {
        setSelectedCountry('');
        setSelectedChartData(null);
      }
    } catch (err: any) {
      setToast({ message: parseApiError(err), type: 'error' });
    }
  };

  const handleToggleChart = async (countryCode: string, enabled: boolean) => {
    try {
      await chartsApi.updateChart(countryCode, { enabled: !enabled });
      await loadChartSubscriptions();
      setToast({ 
        message: enabled 
          ? (t('admin.charts.disabled') || 'Chart disabled') 
          : (t('admin.charts.enabled') || 'Chart enabled'), 
        type: 'success' 
      });
    } catch (err: any) {
      setToast({ message: parseApiError(err), type: 'error' });
    }
  };

  const handleUpdateTopN = async (countryCode: string, topN: number) => {
    try {
      await chartsApi.updateChart(countryCode, { top_n_artists: topN });
      await loadChartSubscriptions();
      setToast({ message: t('admin.charts.updated') || 'Chart updated successfully', type: 'success' });
    } catch (err: any) {
      setToast({ message: parseApiError(err), type: 'error' });
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
              {category.charAt(0).toUpperCase() + category.slice(1)} {t('admin.settings.title')}
            </SectionHeader>
            
            <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10 space-y-4">
              {categorySettings.map(setting => (
                <div key={setting.key} className="flex items-center justify-between py-3 border-b border-slate-200 dark:border-white/10 last:border-0">
                  <div className="flex-1 mr-4">
                    <label className="font-semibold text-foreground block mb-1">
                      {setting.key.split('.')[1].replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </label>
                    <p className="text-sm text-muted-foreground">{setting.description}</p>
                  </div>
                  
                  <div className="flex-shrink-0">
                    {setting.type === 'bool' ? (
                      <button
                        onClick={() => handleSettingChange(setting.key, !editedSettings[setting.key], setting.type)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                          editedSettings[setting.key]
                            ? 'bg-blue-600 dark:bg-red-600'
                            : 'bg-slate-300 dark:bg-zinc-700'
                        }`}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                            editedSettings[setting.key] ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    ) : setting.type === 'int' ? (
                      <input
                        type="number"
                        value={editedSettings[setting.key] || ''}
                        onChange={(e) => handleSettingChange(setting.key, e.target.value, setting.type)}
                        className="w-24 px-3 py-2 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground text-center focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600"
                      />
                    ) : Array.isArray(setting.allowed_values) && setting.allowed_values.length > 0 ? (
                      <Select
                        value={editedSettings[setting.key] || ''}
                        onChange={(value) => handleSettingChange(setting.key, value, setting.type)}
                        options={setting.allowed_values}
                        className="w-48"
                      />
                    ) : (
                      <input
                        type="text"
                        value={editedSettings[setting.key] || ''}
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
            {t('admin.settings.save')} {t('admin.settings.title')}
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

    return (
      <div className="space-y-6">
        {/* Country Selection */}
        <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10">
          <h3 className="text-lg font-semibold text-foreground mb-4">
            {t('admin.charts.selectCountry') || 'Select a Country Chart'}
          </h3>
          
          <div className="flex gap-4">
            <div className="flex-1">
              <Select
                value={selectedCountry}
                onChange={handleCountrySelect}
                options={[
                  { value: '', label: t('admin.charts.selectCountry') || '-- Select Country --' },
                  ...availableCountries.map(c => ({
                    value: c.code,
                    label: `${c.flag} ${c.name}`
                  }))
                ]}
                placeholder={t('admin.charts.selectCountry')}
              />
            </div>

            {selectedCountry && !followedCountryCodes.has(selectedCountry) && (
              <Button
                onClick={handleFollowChart}
                variant="primary"
                disabled={loadingChart}
              >
                + {t('admin.charts.followChart') || 'Follow Chart'}
              </Button>
            )}
          </div>

          {/* Chart Preview */}
          {loadingChart && (
            <div className="mt-4 flex items-center justify-center py-8">
              <Spinner />
            </div>
          )}

          {selectedChartData && !loadingChart && (
            <div className="mt-4 glass rounded-xl p-4 border border-slate-200/50 dark:border-white/10">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="text-3xl">{getCountry(selectedCountry)?.flag}</span>
                  <div>
                    <h4 className="font-semibold text-foreground">{getCountry(selectedCountry)?.name}</h4>
                    <p className="text-sm text-muted-foreground">
                      Top 40 Artists Preview
                    </p>
                  </div>
                </div>
              </div>
              
              {/* Artists Grid Preview */}
              <ChartArtistGrid 
                artists={selectedChartData.artists.slice(0, 40)} 
                maxHeight="200px"
              />
            </div>
          )}
        </div>

        {/* Current Subscriptions */}
        <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10">
          <h3 className="text-lg font-semibold text-foreground mb-4">
            {t('admin.charts.currentSubscriptions') || 'Current Chart Subscriptions'}
          </h3>

          {chartSubscriptions.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <span className="text-5xl mb-3 block">📊</span>
              <p>{t('admin.charts.noSubscriptions') || 'No charts followed yet'}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-slate-200 dark:border-white/10">
                  <tr className="text-left text-sm font-semibold text-muted-foreground">
                    <th className="pb-3">{t('admin.charts.country') || 'Country'}</th>
                    <th className="pb-3">{t('admin.charts.topArtists') || 'Top Artists'}</th>
                    <th className="pb-3">{t('admin.charts.status') || 'Status'}</th>
                    <th className="pb-3">{t('admin.charts.lastSynced') || 'Last Synced'}</th>
                    <th className="pb-3 text-center">{t('admin.charts.actions') || 'Actions'}</th>
                  </tr>
                </thead>
                <tbody>
                  {chartSubscriptions.map((sub) => {
                    const country = getCountry(sub.country_code);
                    if (!country) return null;

                    return (
                      <tr key={sub.id} className="border-b border-slate-200 dark:border-white/10 last:border-0">
                        <td className="py-4">
                          <div className="flex items-center gap-2">
                            <span className="text-2xl">{country.flag}</span>
                            <span className="font-medium text-foreground">{country.name}</span>
                          </div>
                        </td>
                        <td className="py-4">
                          <input
                            type="number"
                            min="1"
                            max="100"
                            value={sub.top_n_artists}
                            onChange={(e) => {
                              const val = parseInt(e.target.value);
                              if (val >= 1 && val <= 100) {
                                handleUpdateTopN(sub.country_code, val);
                              }
                            }}
                            className="w-20 px-2 py-1 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground text-center focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600"
                          />
                        </td>
                        <td className="py-4">
                          <button
                            onClick={() => handleToggleChart(sub.country_code, sub.enabled)}
                            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                              sub.enabled
                                ? 'bg-green-500/20 text-green-600 dark:text-green-400'
                                : 'bg-slate-500/20 text-slate-600 dark:text-slate-400'
                            }`}
                          >
                            {sub.enabled 
                              ? (t('admin.charts.enabled') || 'Enabled')
                              : (t('admin.charts.disabled') || 'Disabled')
                            }
                          </button>
                        </td>
                        <td className="py-4 text-sm text-muted-foreground">
                          {sub.last_synced_at 
                            ? new Date(sub.last_synced_at).toLocaleString()
                            : (t('admin.charts.neverSynced') || 'Never')
                          }
                        </td>
                        <td className="py-4 text-center">
                          <button
                            onClick={() => handleUnfollowChart(sub.country_code)}
                            className="px-3 py-1 rounded-lg bg-red-500/10 text-red-600 dark:text-red-400 hover:bg-red-500/20 transition-all text-sm"
                          >
                            {t('admin.charts.unfollowChart') || 'Unfollow'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderUsersTab = () => {
    const roleColors: Record<string, string> = {
      administrator: 'bg-purple-500/20 text-purple-600 dark:text-purple-400',
      member: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
      visitor: 'bg-slate-500/20 text-slate-600 dark:text-slate-400',
    };

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
                placeholder={t('admin.users.search') || 'Search by username or email...'}
                showClearButton
                onClear={() => setSearchQuery('')}
              />
            </div>

            {/* Status Filter */}
            <Select
              value={statusFilter}
              onChange={(value) => setStatusFilter(value as any)}
              options={[
                { value: 'all', label: t('admin.users.allStatuses') || 'All Statuses' },
                { value: 'active', label: t('admin.users.active') || 'Active' },
                { value: 'inactive', label: t('admin.users.inactive') || 'Inactive' },
              ]}
            />

            {/* Role Filter */}
            <Select
              value={roleFilter}
              onChange={(value) => setRoleFilter(value as any)}
              options={[
                { value: 'all', label: t('admin.users.allRoles') || 'All Roles' },
                { value: 'administrator', label: 'Administrator' },
                { value: 'member', label: 'Member' },
                { value: 'visitor', label: 'Visitor' },
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
            {t('admin.users.showing') || 'Showing'} {filteredUsers.length} {t('admin.users.of') || 'of'} {users.length} {t('admin.users.users') || 'users'}
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
                    {t('admin.users.role')}
                  </th>
                  <th className="px-6 py-4 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wider">
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
                        <p>{t('admin.users.noResults') || 'No users found'}</p>
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
                          options={[
                            { value: 'visitor', label: 'Visitor' },
                            { value: 'member', label: 'Member' },
                            { value: 'administrator', label: 'Administrator' },
                          ]}
                          disabled={u.id === user?.id}
                          className={`text-xs font-medium ${roleColors[u.role]} border-0 py-1`}
                        />
                      </td>
                      <td className="px-6 py-4 text-center">
                        <button
                          onClick={() => toggleUserStatus(u.id, u.is_active)}
                          disabled={u.id === user?.id}
                          className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors disabled:opacity-50 ${
                            u.is_active
                              ? 'bg-green-500/20 text-green-600 dark:text-green-400 hover:bg-green-500/30'
                              : 'bg-red-500/20 text-red-600 dark:text-red-400 hover:bg-red-500/30'
                          }`}
                        >
                          {u.is_active ? t('admin.users.active') : t('admin.users.inactive')}
                        </button>
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
            setToast({ message: t('admin.users.created') || 'User created successfully', type: 'success' });
          }}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        title={t('admin.users.deleteTitle') || 'Delete User'}
        message={
          deleteConfirm
            ? (t('admin.users.confirmDelete', { username: deleteConfirm.username }) || 
               `Are you sure you want to delete user "${deleteConfirm.username}"? This action cannot be undone.`)
            : ''
        }
        confirmText={t('admin.users.delete') || 'Delete'}
        cancelText={t('common.cancel') || 'Cancel'}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirm(null)}
        variant="danger"
      />

      {/* Follow Chart Modal */}
      {showFollowModal && selectedCountry && (
        <FollowChartModal
          country={getCountry(selectedCountry)!}
          onClose={() => setShowFollowModal(false)}
          onSuccess={async () => {
            await loadChartSubscriptions();
            setToast({ message: t('admin.charts.followed') || 'Chart followed successfully', type: 'success' });
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