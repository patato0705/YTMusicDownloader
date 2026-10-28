// src/components/ui/PageStatus.tsx
/**
 * The states a page or a panel shows instead of (or above) its content:
 * loading, failed, empty.
 */
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Spinner } from './Spinner';
import { Icon } from './icons';
import type { IconName } from './icons';

interface LoadingStateProps {
  /** Defaults to "Loading..." */
  message?: string;
  className?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({ message, className = 'py-20' }) => {
  const { t } = useI18n();
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <div className="text-center">
        <Spinner size="lg" className="mx-auto mb-4 text-accent-600 dark:text-accent-500" />
        <p className="text-muted-foreground">{message ?? t('common.loading')}</p>
      </div>
    </div>
  );
};

interface ErrorBannerProps {
  /** A heading above the message, for page-level errors */
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({ title, children, className = '' }) => (
  <div
    role="alert"
    className={`bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl border border-red-500/20 ${title ? 'p-6' : 'p-4'} ${className}`}
  >
    <div className="flex items-center gap-3">
      <Icon name="warning" className={`shrink-0 text-red-600 dark:text-red-400 ${title ? 'w-6 h-6' : 'w-5 h-5'}`} />
      {title ? (
        <div>
          <h3 className="font-semibold text-red-600 dark:text-red-400 mb-1">{title}</h3>
          <p className="text-sm text-red-600/80 dark:text-red-400/80">{children}</p>
        </div>
      ) : (
        <p className="text-sm text-red-600 dark:text-red-400 font-medium">{children}</p>
      )}
    </div>
  </div>
);

interface EmptyStateProps {
  icon: IconName;
  title: string;
  /** Description and actions, under the title */
  children?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ icon, title, children }) => (
  <div className="text-center bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-12 md:p-16 border border-slate-200/50 dark:border-white/10">
    <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-accent-100 dark:bg-accent-950/50 text-accent-600 dark:text-accent-400 mb-5">
      <Icon name={icon} className="w-8 h-8" />
    </div>
    <h3 className="text-2xl font-bold mb-3 text-foreground">{title}</h3>
    {children && <div className="text-muted-foreground max-w-md mx-auto space-y-6">{children}</div>}
  </div>
);
