// src/pages/auth/ChangePassword.tsx
import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useI18n } from '../../contexts/I18nContext';
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
      setError(err.message || 'Failed to change password');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-secondary px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h2 className="text-4xl font-bold text-foreground mb-2">
            {t('auth.changePassword.title')}
          </h2>
          {forced && message && (
            <div className="bg-yellow-500/10 border border-yellow-500 text-yellow-600 dark:text-yellow-500 px-4 py-3 rounded-lg mt-4">
              ⚠️ {message}
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6 bg-card p-8 rounded-xl shadow-2xl border border-border">
          {error && (
            <div className="bg-red-500/10 border border-red-500 text-red-500 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label htmlFor="currentPassword" className="block text-sm font-medium text-card-foreground mb-2">
                {t('auth.changePassword.current')}
              </label>
              <input
                id="currentPassword"
                type="password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="w-full px-4 py-3 bg-background border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
              />
            </div>

            <div>
              <label htmlFor="newPassword" className="block text-sm font-medium text-card-foreground mb-2">
                {t('auth.changePassword.new')}
              </label>
              <input
                id="newPassword"
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-4 py-3 bg-background border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
              />
              <p className="text-xs text-muted-foreground mt-1">
                {t('auth.errors.passwordTooShort')}
              </p>
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-card-foreground mb-2">
                {t('auth.changePassword.confirm')}
              </label>
              <input
                id="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-4 py-3 bg-background border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 px-4 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-lg transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background"
          >
            {isLoading ? t('common.loading') : t('auth.changePassword.button')}
          </button>

          {!forced && (
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="w-full py-3 px-4 bg-secondary hover:bg-secondary/80 text-secondary-foreground font-semibold rounded-lg transition duration-200"
            >
              {t('common.cancel')}
            </button>
          )}
        </form>
      </div>
    </div>
  );
};