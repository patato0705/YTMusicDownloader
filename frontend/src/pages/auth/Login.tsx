// src/pages/auth/Login.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { AuthCard, AuthLayout } from '../../components/layout/AuthLayout';
import { Button } from '../../components/ui/Button';
import { FormField, inputClass } from '../../components/ui/FormField';
import { PasswordInput } from '../../components/ui/PasswordInput';
import { ErrorBanner } from '../../components/ui/PageStatus';
import { Spinner } from '../../components/ui/Spinner';
import { retryAfterMinutes } from '../../utils';
import * as authApi from '../../api/auth';
import type { AuthConfig } from '../../api/auth';

const SSO_ERRORS = ['denied', 'not_allowed', 'inactive', 'unavailable'];

export default function Login(): JSX.Element {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [usernameError, setUsernameError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { login, isAuthenticated } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Which sign-in methods to offer. If it can't be read, fall back to the
  // password form: the server still enforces whatever is really enabled.
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  useEffect(() => {
    authApi.getAuthConfig()
      .then(setAuthConfig)
      .catch(() => setAuthConfig({
        password_login_enabled: true,
        registration_enabled: false,
        oidc_enabled: false,
        oidc_provider_name: null,
        oidc_roles_from_groups: false,
      }));
  }, []);

  // Single sign-on failures come back as /login?oidc_error=<reason>
  const ssoErrorCode = searchParams.get('oidc_error');
  const ssoError = ssoErrorCode
    ? t(`auth.login.ssoErrors.${SSO_ERRORS.includes(ssoErrorCode) ? ssoErrorCode : 'failed'}`)
    : '';
  const shownError = error || ssoError;

  useEffect(() => {
    if (isAuthenticated) navigate('/');
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setUsernameError(username ? '' : t('auth.errors.usernameRequired'));
    setPasswordError(password ? '' : t('auth.errors.passwordRequired'));
    if (!username || !password) return;

    setIsLoading(true);
    try {
      await login(username, password);
      // A temporary password (first admin, admin reset) is caught by
      // ProtectedRoute, which sends the user to /change-password
      navigate('/');
    } catch (err: any) {
      if (err?.status === 429) {
        setError(t('auth.errors.tooManyAttempts', { minutes: retryAfterMinutes(err) }));
      } else {
        setError(t(err?.status === 401 ? 'auth.errors.invalidCredentials' : 'auth.errors.loginFailed'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthLayout title={t('auth.login.title')} subtitle={t('auth.login.subtitle')}>
      <AuthCard>
        {!authConfig ? (
          <div className="flex justify-center py-8">
            <Spinner size="lg" className="text-accent-600 dark:text-accent-500" />
          </div>
        ) : (
          <div className="space-y-6">
            {shownError && <ErrorBanner>{shownError}</ErrorBanner>}

            {authConfig.oidc_enabled && (
              <Button
                type="button"
                variant={authConfig.password_login_enabled ? 'outline' : 'primary'}
                size="lg"
                onClick={authApi.startSingleSignOn}
                className="w-full"
              >
                {t('auth.login.sso', { name: authConfig.oidc_provider_name ?? 'SSO' })}
              </Button>
            )}

            {authConfig.oidc_enabled && authConfig.password_login_enabled && (
              <div className="flex items-center gap-3">
                <div className="h-px flex-1 bg-slate-200 dark:bg-white/10" />
                <span className="text-xs text-muted-foreground">{t('common.or')}</span>
                <div className="h-px flex-1 bg-slate-200 dark:bg-white/10" />
              </div>
            )}

            {authConfig.password_login_enabled && (
              <form onSubmit={handleSubmit} noValidate className="space-y-6">
                <FormField id="username" label={t('auth.login.username')} error={usernameError}>
                  <input
                    id="username"
                    type="text"
                    autoComplete="username"
                    required
                    value={username}
                    onChange={(e) => {
                      setUsername(e.target.value);
                      setUsernameError('');
                    }}
                    className={inputClass(usernameError)}
                    placeholder={t('auth.login.username')}
                    disabled={isLoading}
                  />
                </FormField>

                <FormField id="password" label={t('auth.login.password')} error={passwordError}>
                  <PasswordInput
                    id="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      setPasswordError('');
                    }}
                    className={inputClass(passwordError)}
                    placeholder="••••••••"
                    disabled={isLoading}
                  />
                </FormField>

                <Button type="submit" variant="primary" size="lg" isLoading={isLoading} className="w-full">
                  {isLoading ? t('auth.login.loading') : t('auth.login.button')}
                </Button>
              </form>
            )}

            {authConfig.registration_enabled && (
              <div className="text-center pt-4 border-t border-slate-200 dark:border-white/10">
                <p className="text-sm text-muted-foreground">
                  {t('auth.login.noAccount')}{' '}
                  <Link
                    to="/register"
                    className="font-semibold text-accent-600 dark:text-accent-400 hover:text-accent-700 dark:hover:text-accent-300 transition-colors"
                  >
                    {t('auth.login.register')}
                  </Link>
                </p>
              </div>
            )}
          </div>
        )}
      </AuthCard>
    </AuthLayout>
  );
}
