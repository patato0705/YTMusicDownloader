// src/pages/auth/ChangePassword.tsx
import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../../components/ui/Button';
import * as authApi from '../../api/auth';

export const ChangePassword: React.FC = () => {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  
  const forced = location.state?.forced || false;
  const message = location.state?.message || '';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (newPassword.length < 8) {
      setError(t('auth.errors.passwordTooShort'));
      return;
    }

    if (newPassword !== confirmPassword) {
      setError(t('auth.errors.passwordMismatch'));
      return;
    }

    setIsLoading(true);

    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });

      navigate('/');
    } catch (err: any) {
      setError(err.message || t('auth.errors.changePasswordFailed') || 'Failed to change password');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 relative overflow-hidden bg-background">
      {/* Background effects */}
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
      
      {/* Static background orbs */}
      <div className="fixed top-20 left-20 w-96 h-96 bg-blue-500/20 dark:bg-red-500/20 rounded-full blur-3xl" />
      <div className="fixed bottom-20 right-20 w-96 h-96 bg-indigo-500/20 dark:bg-red-700/20 rounded-full blur-3xl" />
      
      {/* Main content */}
      <div className="relative z-10 max-w-md w-full">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">
            <span className="text-gradient">{t('auth.changePassword.title')}</span>
          </h1>
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent to-blue-500 dark:to-red-500" />
            <span className="text-xl">🔐</span>
            <div className="h-px flex-1 bg-gradient-to-l from-transparent to-blue-500 dark:to-red-500" />
          </div>
          <p className="text-muted-foreground text-lg">
            {t('auth.changePassword.subtitle') || 'Keep your account secure'}
          </p>
        </div>

        {/* Warning message for forced password change */}
        {forced && message && (
          <div className="mb-6 bg-yellow-500/10 dark:bg-yellow-500/5 backdrop-blur-sm rounded-2xl p-5 border border-yellow-500/30">
            <div className="flex items-start gap-3">
              <span className="text-2xl">⚠️</span>
              <div>
                <h3 className="font-semibold text-yellow-600 dark:text-yellow-400 mb-1">
                  {t('auth.changePassword.required') || 'Action Required'}
                </h3>
                <p className="text-sm text-yellow-600/80 dark:text-yellow-400/80">{message}</p>
              </div>
            </div>
          </div>
        )}

        {/* Change password form */}
        <div className="glass rounded-3xl p-8 md:p-10 border-gradient shadow-2xl">
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Error message */}
            {error && (
              <div className="bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl p-4 border border-red-500/20">
                <div className="flex items-center gap-3">
                  <span className="text-xl">⚠️</span>
                  <p className="text-sm text-red-600 dark:text-red-400 font-medium">{error}</p>
                </div>
              </div>
            )}

            {/* Current password field */}
            <div>
              <label htmlFor="currentPassword" className="block text-sm font-semibold text-foreground mb-2">
                {t('auth.changePassword.current')}
              </label>
              <input
                id="currentPassword"
                type="password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 focus:border-transparent transition-all duration-300"
                placeholder="••••••••"
                disabled={isLoading}
              />
            </div>

            {/* New password field */}
            <div>
              <label htmlFor="newPassword" className="block text-sm font-semibold text-foreground mb-2">
                {t('auth.changePassword.new')}
              </label>
              <input
                id="newPassword"
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 focus:border-transparent transition-all duration-300"
                placeholder="••••••••"
                disabled={isLoading}
              />
              <p className="text-xs text-muted-foreground mt-1.5">
                {t('auth.errors.passwordTooShort')}
              </p>
            </div>

            {/* Confirm password field */}
            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-semibold text-foreground mb-2">
                {t('auth.changePassword.confirm')}
              </label>
              <input
                id="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 focus:border-transparent transition-all duration-300"
                placeholder="••••••••"
                disabled={isLoading}
              />
            </div>

            {/* Submit button */}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              isLoading={isLoading}
              className="w-full mt-6"
            >
              {isLoading ? t('common.loading') : t('auth.changePassword.button')}
            </Button>

            {/* Cancel button - only show if not forced */}
            {!forced && (
              <Button
                type="button"
                variant="ghost"
                size="lg"
                onClick={() => navigate(-1)}
                className="w-full"
                disabled={isLoading}
              >
                {t('common.cancel')}
              </Button>
            )}
          </form>
        </div>

        {/* Security note */}
        <div className="mt-6 glass rounded-2xl p-4 border-gradient">
          <div className="flex items-start gap-3">
            <span className="text-lg">💡</span>
            <div className="text-xs text-muted-foreground">
              <p className="font-semibold text-foreground mb-1">
                {t('auth.changePassword.tips.title') || 'Password Tips'}
              </p>
              <ul className="space-y-1">
                <li>• {t('auth.changePassword.tips.length') || 'Use at least 8 characters'}</li>
                <li>• {t('auth.changePassword.tips.mix') || 'Mix uppercase, lowercase, numbers'}</li>
                <li>• {t('auth.changePassword.tips.unique') || 'Don\'t reuse old passwords'}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};