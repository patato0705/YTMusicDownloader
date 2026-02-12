// src/components/ProtectedRoute.tsx
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { Spinner } from './ui/Spinner';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: 'administrator' | 'member' | 'visitor';
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ 
  children, 
  requiredRole 
}) => {
  const { isAuthenticated, isLoading, user } = useAuth();
  const { t } = useI18n();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-background">
        {/* Background effects */}
        <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        <div className="relative z-10 text-center">
          <Spinner size="lg" className="mx-auto mb-4 text-blue-600 dark:text-red-500" />
          <p className="text-muted-foreground">{t('common.loading')}</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Check role if required
  if (requiredRole && user) {
    const roleHierarchy: Record<string, number> = {
      administrator: 3,
      member: 2,
      visitor: 1,
    };

    const userRoleLevel = roleHierarchy[user.role] || 0;
    const requiredRoleLevel = roleHierarchy[requiredRole] || 0;

    if (userRoleLevel < requiredRoleLevel) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-background px-4">
          {/* Background effects */}
          <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
          <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
          
          <div className="relative z-10 max-w-md w-full">
            <div className="glass rounded-2xl border-slate-200 dark:border-white/10 shadow-xl p-8 text-center">
              <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-red-100 to-orange-100 dark:from-red-950/40 dark:to-orange-950/40 mb-6">
                <span className="text-4xl">🔒</span>
              </div>
              <h2 className="text-2xl font-bold mb-3">
                <span className="text-gradient">Access Denied</span>
              </h2>
              <p className="text-muted-foreground mb-6">
                You need <span className="font-semibold text-foreground">{requiredRole}</span> privileges to access this page.
              </p>
              <Navigate to="/" replace />
            </div>
          </div>
        </div>
      );
    }
  }

  return <>{children}</>;
};