// src/pages/auth/ChangePassword.tsx
import React, { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { AuthCard, AuthLayout } from '../../components/layout/AuthLayout';
import { Button } from '../../components/ui/Button';
import { FormField, inputClass } from '../../components/ui/FormField';
import { PasswordInput } from '../../components/ui/PasswordInput';
import { ErrorBanner } from '../../components/ui/PageStatus';
import * as authApi from '../../api/auth';
import { confirmErrorKey, passwordErrorKey, retryAfterMinutes } from '../../utils';

export default function ChangePassword(): JSX.Element {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [currentPasswordError, setCurrentPasswordError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [confirmError, setConfirmError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { t } = useI18n();
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const keyText = (key: string | null) => (key ? t(key) : '');

  // Temporary password (first admin, or reset by an admin): no way out but changing it
  const forced = !!user?.must_change_password;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const currentProblem = currentPassword ? '' : t('auth.errors.currentPasswordRequired');
    const passwordProblem = keyText(passwordErrorKey(newPassword, 'auth.errors.newPasswordRequired'));
    const confirmProblem = keyText(confirmErrorKey(confirmPassword, newPassword, 'auth.errors.confirmPasswordRequired'));
    setCurrentPasswordError(currentProblem);
    setPasswordError(passwordProblem);
    setConfirmError(confirmProblem);
    if (currentProblem || passwordProblem || confirmProblem) return;

    setIsLoading(true);
    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });

      // Picks up the cleared must_change_password, or ProtectedRoute would
      // send us straight back here
      await refreshUser();
      navigate('/', { replace: true });
    } catch (err: any) {
      if (err?.status === 400) {
        setCurrentPasswordError(t('auth.errors.currentPasswordIncorrect'));
      } else if (err?.status === 429) {
        setError(t('auth.errors.tooManyAttempts', { minutes: retryAfterMinutes(err) }));
      } else {
        setError(t('auth.errors.changePasswordFailed'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Single sign-on accounts have no password to change here
  if (user && !user.has_password) {
    return <Navigate to="/" replace />;
  }

  return (
    <AuthLayout title={t('auth.changePassword.title')} emoji="🔐" subtitle={t('auth.changePassword.subtitle')}>
      {forced && (
        <div className="mb-6 bg-yellow-500/10 dark:bg-yellow-500/5 backdrop-blur-sm rounded-2xl p-5 border border-yellow-500/30">
          <div className="flex items-start gap-3">
            <span className="text-2xl" aria-hidden="true">⚠️</span>
            <div>
              <h3 className="font-semibold text-yellow-600 dark:text-yellow-400 mb-1">
                {t('auth.changePassword.required')}
              </h3>
              <p className="text-sm text-yellow-600/80 dark:text-yellow-400/80">{t('auth.changePassword.temporaryWarning')}</p>
            </div>
          </div>
        </div>
      )}

      <AuthCard>
        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {error && <ErrorBanner>{error}</ErrorBanner>}

          <FormField id="currentPassword" label={t('auth.changePassword.current')} error={currentPasswordError}>
            <PasswordInput
              id="currentPassword"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(e) => {
                setCurrentPassword(e.target.value);
                setCurrentPasswordError('');
              }}
              className={inputClass(currentPasswordError)}
              placeholder="••••••••"
              disabled={isLoading}
            />
          </FormField>

          <FormField id="newPassword" label={t('auth.changePassword.new')} error={passwordError} hint={t('auth.errors.passwordTooShort')}>
            <PasswordInput
              id="newPassword"
              autoComplete="new-password"
              required
              value={newPassword}
              onChange={(e) => {
                setNewPassword(e.target.value);
                setPasswordError(keyText(passwordErrorKey(e.target.value)));
              }}
              className={inputClass(passwordError)}
              placeholder="••••••••"
              disabled={isLoading}
            />
          </FormField>

          <FormField id="confirmPassword" label={t('auth.changePassword.confirm')} error={confirmError}>
            <PasswordInput
              id="confirmPassword"
              autoComplete="new-password"
              required
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                setConfirmError(keyText(confirmErrorKey(e.target.value, newPassword)));
              }}
              className={inputClass(confirmError)}
              placeholder="••••••••"
              disabled={isLoading}
            />
          </FormField>

          <Button type="submit" variant="primary" size="lg" isLoading={isLoading} className="w-full mt-6">
            {isLoading ? t('common.loading') : t('auth.changePassword.button')}
          </Button>

          {!forced && (
            <Button type="button" variant="ghost" size="lg" onClick={() => navigate(-1)} className="w-full" disabled={isLoading}>
              {t('common.cancel')}
            </Button>
          )}
        </form>
      </AuthCard>

      <div className="mt-6 glass rounded-2xl p-4 border-gradient">
        <div className="flex items-start gap-3">
          <span className="text-lg" aria-hidden="true">💡</span>
          <div className="text-xs text-muted-foreground">
            <p className="font-semibold text-foreground mb-1">{t('auth.changePassword.tips.title')}</p>
            <ul className="space-y-1">
              <li>• {t('auth.changePassword.tips.length')}</li>
              <li>• {t('auth.changePassword.tips.mix')}</li>
              <li>• {t('auth.changePassword.tips.unique')}</li>
            </ul>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}
