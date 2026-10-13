// src/components/ui/PageStatus.tsx
/**
 * The states a page or a panel shows instead of (or above) its content:
 * loading, failed, empty.
 */
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Spinner } from './Spinner';

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
        <Spinner size="lg" className="mx-auto mb-4 text-blue-600 dark:text-red-500" />
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
      <span className={title ? 'text-2xl' : 'text-xl'} aria-hidden="true">⚠️</span>
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
  /** An emoji */
  icon: string;
  title: string;
  /** Description and actions, under the title */
  children?: React.ReactNode;
  /** Drop the card around it, when it already sits in one */
  bare?: boolean;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ icon, title, children, bare = false }) => (
  <div
    className={`text-center ${
      bare ? 'py-16' : 'bg-white/40 dark:bg-white/5 backdrop-blur-md rounded-3xl p-12 md:p-16 border border-slate-200/50 dark:border-white/10'
    }`}
  >
    <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-red-950/40 dark:to-red-900/30 mb-6">
      <span className="text-5xl" aria-hidden="true">{icon}</span>
    </div>
    <h3 className="text-2xl font-bold mb-3 text-foreground">{title}</h3>
    {children && <div className="text-muted-foreground max-w-md mx-auto space-y-6">{children}</div>}
  </div>
);
