// src/components/admin/AdminTabShell.tsx
/**
 * Common frame for an admin tab: a spinner while its data first loads, an
 * error banner when a load failed, otherwise the tab's content.
 */
import React from 'react';
import { ErrorBanner, LoadingState } from '../ui/PageStatus';

export interface AdminTabProps {
  onToast: (message: string, type: 'success' | 'error') => void;
}

interface AdminTabShellProps {
  loading: boolean;
  error: string | null;
  children: React.ReactNode;
}

export const AdminTabShell: React.FC<AdminTabShellProps> = ({ loading, error, children }) => {
  if (loading) return <LoadingState />;

  return (
    <>
      {error && <ErrorBanner className="mb-8">{error}</ErrorBanner>}
      {children}
    </>
  );
};
