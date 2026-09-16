// src/components/admin/AdminTabShell.tsx
/**
 * Common frame for an admin tab: a spinner while its data first loads, an
 * error banner when a load failed, otherwise the tab's content.
 */
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Spinner } from '../ui/Spinner';

export interface AdminTabProps {
  onToast: (message: string, type: 'success' | 'error') => void;
}

interface AdminTabShellProps {
  loading: boolean;
  error: string | null;
  children: React.ReactNode;
}

export const AdminTabShell: React.FC<AdminTabShellProps> = ({ loading, error, children }) => {
  const { t } = useI18n();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <Spinner size="lg" className="mx-auto mb-4 text-blue-600 dark:text-red-500" />
          <p className="text-muted-foreground">{t('common.loading')}</p>
        </div>
      </div>
    );
  }

  return (
    <>
      {error && (
        <div className="mb-8 bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl p-4 border border-red-500/20">
          <div className="flex items-center gap-3">
            <span className="text-xl">⚠️</span>
            <p className="text-sm text-red-600 dark:text-red-400 font-medium">{error}</p>
          </div>
        </div>
      )}
      {children}
    </>
  );
};
