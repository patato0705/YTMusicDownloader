// src/pages/auth/Register.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { AuthCard, AuthLayout } from '../../components/layout/AuthLayout';
import { Button } from '../../components/ui/Button';
import { FormField, inputClass } from '../../components/ui/FormField';
import { PasswordInput } from '../../components/ui/PasswordInput';
import { ErrorBanner, LoadingState } from '../../components/ui/PageStatus';
import * as authApi from '../../api/auth';
import { confirmErrorKey, invalidFields, passwordErrorKey, usernameErrorKey } from '../../utils';

export default function Register(): JSX.Element {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [usernameError, setUsernameError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [confirmError, setConfirmError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // null while checking whether public registration is on
  const [registrationEnabled, setRegistrationEnabled] = useState<boolean | null>(null);

  const { login, isAuthenticated } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const keyText = (key: string | null) => (key ? t(key) : '');

  useEffect(() => {
    if (isAuthenticated) navigate('/');
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    authApi.getAuthConfig()
      .then((config) => setRegistrationEnabled(config.registration_enabled))
      .catch((err) => {
        console.error('Failed to check registration status:', err);
        // Shown anyway: the backend refuses the submit if it's off
        setRegistrationEnabled(true);
      });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const usernameProblem = keyText(usernameErrorKey(username, 'auth.errors.usernameRequired'));
    const passwordProblem = keyText(passwordErrorKey(password, 'auth.errors.passwordRequired'));
    const confirmProblem = keyText(confirmErrorKey(confirmPassword, password, 'auth.errors.confirmPasswordRequired'));
    setUsernameError(usernameProblem);
    setPasswordError(passwordProblem);
    setConfirmError(confirmProblem);
    if (usernameProblem || passwordProblem || confirmProblem) return;

    setIsLoading(true);
    try {
      await authApi.register({ username, password });
      await login(username, password);
      navigate('/');
    } catch (err: any) {
      // The checks above mirror the backend's, so a 422 is only a safety
      // net: a translated message rather than the validator's English one
      const fields = invalidFields(err);
      if (fields.has('username') || fields.has('password')) {
        if (fields.has('username')) setUsernameError(t('auth.errors.usernameInvalid'));
        if (fields.has('password')) setPasswordError(t('auth.errors.passwordInvalid'));
      } else if (err?.status === 403) {
        setError(t('auth.register.disabled.message'));
      } else if (err?.status === 409 && err.data?.detail === 'username_taken') {
        setUsernameError(t('auth.errors.usernameTaken'));
      } else {
        setError(t('auth.errors.registrationFailed'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  if (registrationEnabled === null) {
    return (
      <AuthLayout>
        <LoadingState />
      </AuthLayout>
    );
  }

  if (!registrationEnabled) {
    return (
      <AuthLayout>
        <AuthCard className="text-center">
          <div className="w-20 h-20 mx-auto rounded-full bg-slate-100 dark:bg-white/10 flex items-center justify-center mb-4">
            <span className="text-4xl" aria-hidden="true">🔒</span>
          </div>
          <h1 className="text-3xl font-bold mb-3">
            <span className="text-gradient">{t('auth.register.disabled.title')}</span>
          </h1>
          <p className="text-muted-foreground mb-6">{t('auth.register.disabled.message')}</p>
          <Button variant="primary" size="lg" className="w-full" onClick={() => navigate('/login')}>
            {t('auth.register.disabled.goToLogin')}
          </Button>
        </AuthCard>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t('auth.register.title')} emoji="✨" subtitle={t('auth.register.subtitle')}>
      <AuthCard>
        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {error && <ErrorBanner>{error}</ErrorBanner>}

          <FormField id="username" label={t('auth.register.username')} error={usernameError} hint={t('auth.register.usernameHint')}>
            <input
              id="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                setUsernameError(keyText(usernameErrorKey(e.target.value)));
              }}
              className={inputClass(usernameError)}
              placeholder={t('auth.register.username')}
              disabled={isLoading}
            />
          </FormField>

          <FormField id="password" label={t('auth.register.password')} error={passwordError} hint={t('auth.errors.passwordTooShort')}>
            <PasswordInput
              id="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setPasswordError(keyText(passwordErrorKey(e.target.value)));
              }}
              className={inputClass(passwordError)}
              placeholder="••••••••"
              disabled={isLoading}
            />
          </FormField>

          <FormField id="confirmPassword" label={t('auth.register.confirmPassword')} error={confirmError}>
            <PasswordInput
              id="confirmPassword"
              autoComplete="new-password"
              required
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                setConfirmError(keyText(confirmErrorKey(e.target.value, password)));
              }}
              className={inputClass(confirmError)}
              placeholder="••••••••"
              disabled={isLoading}
            />
          </FormField>

          <Button type="submit" variant="primary" size="lg" isLoading={isLoading} className="w-full mt-6">
            {isLoading ? t('auth.register.loading') : t('auth.register.button')}
          </Button>

          <div className="text-center pt-4 border-t border-slate-200 dark:border-white/10">
            <p className="text-sm text-muted-foreground">
              {t('auth.register.hasAccount')}{' '}
              <Link
                to="/login"
                className="font-semibold text-blue-600 dark:text-red-400 hover:text-blue-700 dark:hover:text-red-300 transition-colors"
              >
                {t('auth.register.login')}
              </Link>
            </p>
          </div>
        </form>
      </AuthCard>
    </AuthLayout>
  );
}
