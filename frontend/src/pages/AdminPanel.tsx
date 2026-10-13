// src/pages/AdminPanel.tsx
import { useState, useEffect } from 'react';
import { useI18n } from '../contexts/I18nContext';
import { useFeatures } from '../contexts/FeaturesContext';
import { PageHero } from '../components/ui/PageHero';
import { Toast } from '../components/ui/Toast';
import { FilterTabs } from '../components/ui/FilterTabs';
import type { FilterTab } from '../components/ui/FilterTabs';
import { UsersTab } from '../components/admin/UsersTab';
import { ChartsTab } from '../components/admin/ChartsTab';
import { SettingsTab } from '../components/admin/SettingsTab';
import { BackupTab } from '../components/admin/BackupTab';

type Tab = 'users' | 'charts' | 'settings' | 'backup';

// Role gating happens in <ProtectedRoute adminOnly> around this route (App.tsx)
export default function AdminPanel(): JSX.Element {
  const [activeTab, setActiveTab] = useState<Tab>('users');
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
    { id: 'users', icon: '👥', label: t('admin.tabs.users') },
    ...(chartsEnabled ? [{ id: 'charts' as const, icon: '📊', label: t('admin.tabs.charts') }] : []),
    { id: 'settings', icon: '⚙️', label: t('admin.tabs.settings') },
    { id: 'backup', icon: '💾', label: t('admin.tabs.backup') },
  ];

  return (
    <div className="space-y-8 pb-12">
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      <PageHero
        title={
          <>
            <span className="text-foreground">{t('admin.title')} </span>
            <span className="text-gradient">{t('admin.panel')}</span>
          </>
        }
        subtitle={t('admin.subtitle')}
      />

      <FilterTabs tabs={tabs} active={activeTab} onChange={setActiveTab} fill />

      {/* Each tab owns its data and state; switching remounts it */}
      {activeTab === 'users' && <UsersTab onToast={showToast} />}
      {activeTab === 'charts' && <ChartsTab onToast={showToast} />}
      {activeTab === 'settings' && <SettingsTab onToast={showToast} onSaved={refreshFeatures} />}
      {activeTab === 'backup' && <BackupTab onToast={showToast} />}
    </div>
  );
}
