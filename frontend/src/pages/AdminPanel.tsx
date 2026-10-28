// src/pages/AdminPanel.tsx
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useI18n } from '../contexts/I18nContext';
import { useFeatures } from '../contexts/FeaturesContext';
import { PageHeader } from '../components/ui/PageHeader';
import { Toast } from '../components/ui/Toast';
import { FilterTabs } from '../components/ui/FilterTabs';
import type { FilterTab } from '../components/ui/FilterTabs';
import { UsersTab } from '../components/admin/UsersTab';
import { ChartsTab } from '../components/admin/ChartsTab';
import { SettingsTab } from '../components/admin/SettingsTab';
import { BackupTab } from '../components/admin/BackupTab';

const TABS = ['users', 'charts', 'settings', 'backup'] as const;
type Tab = typeof TABS[number];

// Role gating happens in <ProtectedRoute adminOnly> around this route (App.tsx)
export default function AdminPanel(): JSX.Element {
  // ?tab= opens a given tab, e.g. from the empty Charts page
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<Tab>(() => TABS.find((tab) => tab === searchParams.get('tab')) ?? 'users');
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const { features, refreshFeatures } = useFeatures();
  const { t } = useI18n();

  const chartsEnabled = !!features?.charts_enabled;

  // Don't leave the user on a tab that just got switched off
  useEffect(() => {
    if (activeTab === 'charts' && !chartsEnabled) setActiveTab('users');
  }, [activeTab, chartsEnabled]);

  const showToast = (message: string, type: 'success' | 'error') => setToast({ message, type });

  const tabs: FilterTab<Tab>[] = [
    { id: 'users', icon: 'users', label: t('admin.tabs.users') },
    ...(chartsEnabled ? [{ id: 'charts' as const, icon: 'chart' as const, label: t('admin.tabs.charts') }] : []),
    { id: 'settings', icon: 'cog', label: t('admin.tabs.settings') },
    { id: 'backup', icon: 'database', label: t('admin.tabs.backup') },
  ];

  return (
    <div className="space-y-8 pb-12">
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      <PageHeader icon="cog" title={t('nav.admin')} subtitle={t('admin.subtitle')} />

      <FilterTabs tabs={tabs} active={activeTab} onChange={setActiveTab} fill />

      {/* Each tab owns its data and state; switching remounts it */}
      {activeTab === 'users' && <UsersTab onToast={showToast} />}
      {activeTab === 'charts' && <ChartsTab onToast={showToast} />}
      {activeTab === 'settings' && <SettingsTab onToast={showToast} onSaved={refreshFeatures} />}
      {activeTab === 'backup' && <BackupTab onToast={showToast} />}
    </div>
  );
}
