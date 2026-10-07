// src/pages/auth/Login.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { retryAfterMinutes } from '../../utils';
import * as authApi from '../../api/auth';
import type { AuthConfig } from '../../api/auth';

export const Login: React.FC = () => {
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
    ? t(['denied', 'not_allowed', 'inactive', 'unavailable'].includes(ssoErrorCode)
        ? `auth.login.ssoErrors.${ssoErrorCode}`
        : 'auth.login.ssoErrors.failed')
    : '';
  const shownError = error || ssoError;

  // Redirect if already logged in
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setUsernameError('');
    setPasswordError('');

    // Check for empty fields
    if (!username) {
      setUsernameError(t('auth.errors.usernameRequired'));
      return;
    }

    if (!password) {
      setPasswordError(t('auth.errors.passwordRequired'));
      return;
    }

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
            <span className="text-gradient">{t('auth.login.title')}</span>
          </h1>
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent to-blue-500 dark:to-red-500" />
            <span className="text-xl">🎵</span>
            <div className="h-px flex-1 bg-gradient-to-l from-transparent to-blue-500 dark:to-red-500" />
          </div>
          <p className="text-muted-foreground text-lg">{t('auth.login.subtitle')}</p>
        </div>

        {/* Sign-in card */}
        <div className="glass rounded-3xl p-8 md:p-10 border-gradient shadow-2xl">
          {!authConfig ? (
            <div className="flex justify-center py-8">
              <Spinner size="lg" className="text-blue-600 dark:text-red-500" />
            </div>
          ) : (
            <div className="space-y-6">
              {/* Error message */}
              {shownError && (
                <div className="bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl p-4 border border-red-500/20">
                  <div className="flex items-center gap-3">
                    <span className="text-xl">⚠️</span>
                    <p className="text-sm text-red-600 dark:text-red-400 font-medium">{shownError}</p>
                  </div>
                </div>
              )}

              {/* Single sign-on */}
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
                  <span className="text-xs uppercase tracking-wider text-muted-foreground">{t('auth.login.or')}</span>
                  <div className="h-px flex-1 bg-slate-200 dark:bg-white/10" />
                </div>
              )}

              {authConfig.password_login_enabled && (
                <form onSubmit={handleSubmit} noValidate className="space-y-6">
                  {/* Username field */}
                  <div>
                    <label htmlFor="username" className="block text-sm font-semibold text-foreground mb-2">
                      {t('auth.login.username')}
                    </label>
                    <input
                      id="username"
                      type="text"
                      required
                      value={username}
                      onChange={(e) => {
                        setUsername(e.target.value);
                        if (usernameError) setUsernameError('');
                      }}
                      className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${
                        usernameError 
                          ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                          : 'focus:ring-blue-500 dark:focus:ring-red-600'
                      } focus:border-transparent transition-all duration-300`}
                      placeholder={t('auth.login.username')}
                      disabled={isLoading}
                    />
                    {usernameError && (
                      <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
                        <span>⚠️</span>
                        {usernameError}
                      </p>
                    )}
                  </div>

                  {/* Password field */}
                  <div>
                    <label htmlFor="password" className="block text-sm font-semibold text-foreground mb-2">
                      {t('auth.login.password')}
                    </label>
                    <input
                      id="password"
                      type="password"
                      required
                      value={password}
                      onChange={(e) => {
                        setPassword(e.target.value);
                        if (passwordError) setPasswordError('');
                      }}
                      className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${
                        passwordError 
                          ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                          : 'focus:ring-blue-500 dark:focus:ring-red-600'
                      } focus:border-transparent transition-all duration-300`}
                      placeholder="••••••••"
                      disabled={isLoading}
                    />
                    {passwordError && (
                      <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
                        <span>⚠️</span>
                        {passwordError}
                      </p>
                    )}
                  </div>

                  {/* Submit button */}
                  <Button
                    type="submit"
                    variant="primary"
                    size="lg"
                    isLoading={isLoading}
                    className="w-full"
                  >
                    {isLoading ? t('auth.login.loading') : t('auth.login.button')}
                  </Button>
                </form>
              )}

              {/* Register link */}
              {authConfig.registration_enabled && (
                <div className="text-center pt-4 border-t border-slate-200 dark:border-white/10">
                  <p className="text-sm text-muted-foreground">
                    {t('auth.login.noAccount')}{' '}
                    <Link
                      to="/register"
                      className="font-semibold text-blue-600 dark:text-red-400 hover:text-blue-700 dark:hover:text-red-300 transition-colors"
                    >
                      {t('auth.login.register')}
                    </Link>
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};