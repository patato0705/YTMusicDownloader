// src/pages/admin/AdminPanel.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { Button } from '../components/ui/Button';
import { Spinner } from '../components/ui/Spinner';
import { SectionHeader } from '../components/ui/SectionHeader';
import { PageHero } from '../components/ui/PageHero';
import * as adminApi from '../api/admin';
import type { Setting, User } from '../api/admin';

export default function AdminPanel(): JSX.Element {
  const [activeTab, setActiveTab] = useState<'settings' | 'users'>('settings');
  const [settings, setSettings] = useState<Setting[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [editedSettings, setEditedSettings] = useState<Record<string, any>>({});
  
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
      } else {
        await loadUsers();
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
      alert(t('admin.settings.saved') || 'Settings saved successfully');
    } catch (err: any) {
      setError(err.message || 'Failed to save settings');
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
    } catch (err: any) {
      setError(err.message || 'Failed to update user');
    }
  };

  const changeUserRole = async (userId: number, newRole: string) => {
    try {
      await adminApi.updateUserRole(userId, newRole);
      await loadUsers();
    } catch (err: any) {
      setError(err.message || 'Failed to update role');
    }
  };

  const deleteUser = async (userId: number, username: string) => {
    if (!confirm(t('admin.users.confirmDelete', { username }) || `Delete user ${username}?`)) {
      return;
    }

    try {
      await adminApi.deleteUser(userId);
      await loadUsers();
    } catch (err: any) {
      setError(err.message || 'Failed to delete user');
    }
  };

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
            
            <div className="glass rounded-2xl p-6 border-gradient space-y-4">
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
        <div className="glass rounded-2xl overflow-hidden border-gradient">
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
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-foreground">{u.username}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm text-muted-foreground">{u.email}</div>
                    </td>
                    <td className="px-6 py-4">
                      <select
                        value={u.role}
                        onChange={(e) => changeUserRole(u.id, e.target.value)}
                        disabled={u.id === user?.id}
                        className={`px-3 py-1 text-xs font-medium rounded-lg ${roleColors[u.role]} border-0 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 disabled:opacity-50`}
                      >
                        <option value="visitor">Visitor</option>
                        <option value="member">Member</option>
                        <option value="administrator">Administrator</option>
                      </select>
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
                ))}
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
            onClick={() => setActiveTab('settings')}
            className={`px-6 py-3 rounded-xl font-medium transition-all duration-300 ${
              activeTab === 'settings'
                ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
            }`}
          >
            ⚙️ {t('admin.tabs.settings')}
          </button>
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
        </div>

        {/* Tab content */}
        {activeTab === 'settings' ? renderSettingsTab() : renderUsersTab()}
      </div>
    </div>
  );
}