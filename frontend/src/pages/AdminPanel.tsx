// src/pages/AdminPanel.tsx
import React, { useState, useEffect } from 'react';
import { useI18n } from '../contexts/I18nContext';
import { PageHero } from '../components/ui/PageHero';
import { Toast } from '../components/ui/Toast';
import { UsersTab } from '../components/admin/UsersTab';
import { ChartsTab } from '../components/admin/ChartsTab';
import { SettingsTab } from '../components/admin/SettingsTab';
import { BackupTab } from '../components/admin/BackupTab';
import { getFeatures } from '../api/features';
import type { Features } from '../api/features';

type Tab = 'users' | 'charts' | 'settings' | 'backup';

export default function AdminPanel(): JSX.Element {
  const [activeTab, setActiveTab] = useState<Tab>('users');
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  // Feature flags (drive which tabs are shown)
  const [features, setFeatures] = useState<Features | null>(null);

  const { t } = useI18n();

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

  const showToast = (message: string, type: 'success' | 'error') => setToast({ message, type });

  const tabs: { id: Tab; icon: string; visible: boolean }[] = [
    { id: 'users', icon: '👥', visible: true },
    { id: 'charts', icon: '📊', visible: chartsEnabled },
    { id: 'settings', icon: '⚙️', visible: true },
    { id: 'backup', icon: '💾', visible: true },
  ];

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

        {/* Tab navigation */}
        <div className="flex items-center gap-2 glass rounded-2xl p-2 w-fit">
          {tabs.filter(tab => tab.visible).map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-6 py-3 rounded-xl font-medium transition-all duration-300 ${
                activeTab === tab.id
                  ? 'bg-blue-600 dark:bg-red-600 text-white shadow-lg'
                  : 'text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
              }`}
            >
              {tab.icon} {t(`admin.tabs.${tab.id}`)}
            </button>
          ))}
        </div>

        {/* Tab content — each tab owns its data and state; switching remounts it */}
        {activeTab === 'users' && <UsersTab onToast={showToast} />}
        {activeTab === 'charts' && <ChartsTab onToast={showToast} />}
        {activeTab === 'settings' && <SettingsTab onToast={showToast} onSaved={loadFeatures} />}
        {activeTab === 'backup' && <BackupTab onToast={showToast} />}
      </div>
    </div>
  );
}
