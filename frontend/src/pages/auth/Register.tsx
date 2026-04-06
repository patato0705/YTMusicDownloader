// src/pages/auth/Register.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../../components/ui/Button';
import * as authApi from '../../api/auth';

export const Register: React.FC = () => {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [confirmError, setConfirmError] = useState('');
  const [usernameError, setUsernameError] = useState('');
  const [emailError, setEmailError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [registrationEnabled, setRegistrationEnabled] = useState<boolean | null>(null);
  const [checkingRegistration, setCheckingRegistration] = useState(true);
  
  const { login, isAuthenticated } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

  // Redirect if already logged in
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  // Check if registration is enabled using public API endpoint
  useEffect(() => {
    const checkRegistration = async () => {
      try {
        const enabled = await authApi.isRegistrationEnabled();
        setRegistrationEnabled(enabled);
      } catch (err) {
        console.error('Failed to check registration status:', err);
        // On error, assume enabled - backend will validate on submit
        setRegistrationEnabled(true);
      } finally {
        setCheckingRegistration(false);
      }
    };

    checkRegistration();
  }, []);

  // Validate username
  const validateUsername = (name: string) => {
    if (name && name.length < 3) {
      setUsernameError(t('auth.errors.usernameTooShort') || 'Username must be at least 3 characters');
    } else if (name && name.length > 64) {
      setUsernameError(t('auth.errors.usernameTooLong') || 'Username must be at most 64 characters');
    } else {
      setUsernameError('');
    }
  };

  // Validate email format
  const validateEmail = (value: string) => {
    if (value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      setEmailError(t('auth.errors.invalidEmail') || 'Please enter a valid email address');
    } else {
      setEmailError('');
    }
  };

  // Parse API errors from ApiError class (err.data = raw response body)
  const parseApiError = (err: any): string => {
    const data = err.data;

    if (data?.detail && Array.isArray(data.detail)) {
      return data.detail.map((e: any) => {
        const field = e.loc && e.loc.length > 1 ? e.loc[e.loc.length - 1] : null;
        const msg = e.msg || 'Invalid value';
        return field ? `${field}: ${msg}` : msg;
      }).join(', ');
    }

    if (data?.detail && typeof data.detail === 'string') {
      return data.detail;
    }

    return err.message || t('auth.errors.registrationFailed') || 'Registration failed';
  };

  // Validate password
  const validatePassword = (pass: string) => {
    if (pass && pass.length < 8) {
      setPasswordError(t('auth.errors.passwordTooShort'));
    } else {
      setPasswordError('');
    }
  };

  // Validate confirm password
  const validateConfirmPassword = (confirm: string) => {
    if (confirm && password && confirm !== password) {
      setConfirmError(t('auth.errors.passwordMismatch'));
    } else {
      setConfirmError('');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setUsernameError('');
    setEmailError('');
    setPasswordError('');
    setConfirmError('');

    // Check for empty fields
    if (!username) {
      setUsernameError(t('auth.errors.usernameRequired') || 'Username is required');
      return;
    }

    if (!email) {
      setEmailError(t('auth.errors.emailRequired') || 'Email is required');
      return;
    }

    if (!password) {
      setPasswordError(t('auth.errors.passwordRequired') || 'Password is required');
      return;
    }

    if (!confirmPassword) {
      setConfirmError(t('auth.errors.confirmPasswordRequired') || 'Please confirm your password');
      return;
    }

    // Validate username length
    if (username.length < 3) {
      setUsernameError(t('auth.errors.usernameTooShort') || 'Username must be at least 3 characters');
      return;
    }
    if (username.length > 64) {
      setUsernameError(t('auth.errors.usernameTooLong') || 'Username must be at most 64 characters');
      return;
    }

    // Validate password length
    if (password.length < 8) {
      setPasswordError(t('auth.errors.passwordTooShort'));
      return;
    }

    // Validate password match
    if (password !== confirmPassword) {
      setConfirmError(t('auth.errors.passwordMismatch'));
      return;
    }

    setIsLoading(true);

    try {
      await authApi.register({ username, email, password });

      // Auto-login after registration
      await login(username, password);
      navigate('/');
    } catch (err: any) {
      const data = err.data;

      // Route field-specific errors from FastAPI validation
      if (data?.detail && Array.isArray(data.detail)) {
        let hasFieldError = false;
        data.detail.forEach((e: any) => {
          const field = e.loc && e.loc.length > 1 ? e.loc[e.loc.length - 1] : null;
          const msg = e.msg || 'Invalid value';

          if (field === 'username') {
            setUsernameError(msg);
            hasFieldError = true;
          } else if (field === 'email') {
            setEmailError(msg);
            hasFieldError = true;
          } else if (field === 'password') {
            setPasswordError(msg);
            hasFieldError = true;
          }
        });
        if (!hasFieldError) setError(parseApiError(err));
      } else {
        setError(parseApiError(err));
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Loading state while checking registration
  if (checkingRegistration) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 py-12 relative overflow-hidden bg-background">
        <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />
        <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />
        
        <div className="relative z-10 text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-500 dark:border-red-500 border-t-transparent" />
          <p className="text-muted-foreground mt-4">{t('common.loading')}</p>
        </div>
      </div>
    );
  }

  // Registration disabled state
  if (registrationEnabled === false) {
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
          <div className="glass rounded-3xl p-8 md:p-10 border-gradient shadow-2xl text-center">
            <div className="mb-6">
              <div className="w-20 h-20 mx-auto rounded-full bg-slate-100 dark:bg-white/10 flex items-center justify-center mb-4">
                <span className="text-4xl">🔒</span>
              </div>
              <h1 className="text-3xl font-bold mb-3">
                <span className="text-gradient">{t('auth.register.disabled.title') || 'Registration Disabled'}</span>
              </h1>
              <p className="text-muted-foreground mb-6">
                {t('auth.register.disabled.message') || 'Public registration is currently disabled. Please contact an administrator for access.'}
              </p>
            </div>

            <Link to="/login">
              <Button variant="primary" size="lg" className="w-full">
                {t('auth.register.disabled.goToLogin') || 'Go to Login'}
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

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
            <span className="text-gradient">{t('auth.register.title')}</span>
          </h1>
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent to-blue-500 dark:to-red-500" />
            <span className="text-xl">✨</span>
            <div className="h-px flex-1 bg-gradient-to-l from-transparent to-blue-500 dark:to-red-500" />
          </div>
          <p className="text-muted-foreground text-lg">{t('auth.register.subtitle')}</p>
        </div>

        {/* Register form */}
        <div className="glass rounded-3xl p-8 md:p-10 border-gradient shadow-2xl">
          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            {/* Error message */}
            {error && (
              <div className="bg-red-500/10 dark:bg-red-500/5 backdrop-blur-sm rounded-2xl p-4 border border-red-500/20">
                <div className="flex items-center gap-3">
                  <span className="text-xl">⚠️</span>
                  <p className="text-sm text-red-600 dark:text-red-400 font-medium">{error}</p>
                </div>
              </div>
            )}

            {/* Username field */}
            <div>
              <label htmlFor="username" className="block text-sm font-semibold text-foreground mb-2">
                {t('auth.register.username')}
              </label>
              <input
                id="username"
                type="text"
                required
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                  if (e.target.value) {
                    validateUsername(e.target.value);
                  } else {
                    setUsernameError('');
                  }
                }}
                onBlur={(e) => validateUsername(e.target.value)}
                className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${
                  usernameError 
                    ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                    : 'focus:ring-blue-500 dark:focus:ring-red-600'
                } focus:border-transparent transition-all duration-300`}
                placeholder={t('auth.register.username')}
                disabled={isLoading}
              />
              {usernameError ? (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
                  <span>⚠️</span>
                  {usernameError}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground mt-1.5">
                  {t('auth.register.usernameHint') || '3-64 characters'}
                </p>
              )}
            </div>

            {/* Email field */}
            <div>
              <label htmlFor="email" className="block text-sm font-semibold text-foreground mb-2">
                {t('auth.register.email')}
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (e.target.value) validateEmail(e.target.value);
                  else setEmailError('');
                }}
                onBlur={(e) => validateEmail(e.target.value)}
                className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${
                  emailError 
                    ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                    : 'focus:ring-blue-500 dark:focus:ring-red-600'
                } focus:border-transparent transition-all duration-300`}
                placeholder={t('auth.register.mailPlaceholder')}
                disabled={isLoading}
              />
              {emailError && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
                  <span>⚠️</span>
                  {emailError}
                </p>
              )}
            </div>

            {/* Password field */}
            <div>
              <label htmlFor="password" className="block text-sm font-semibold text-foreground mb-2">
                {t('auth.register.password')}
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (e.target.value) {
                    validatePassword(e.target.value);
                  } else {
                    setPasswordError('');
                  }
                }}
                onBlur={(e) => validatePassword(e.target.value)}
                className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${
                  passwordError 
                    ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                    : 'focus:ring-blue-500 dark:focus:ring-red-600'
                } focus:border-transparent transition-all duration-300`}
                placeholder="••••••••"
                disabled={isLoading}
              />
              {passwordError ? (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
                  <span>⚠️</span>
                  {passwordError}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground mt-1.5">
                  {t('auth.errors.passwordTooShort')}
                </p>
              )}
            </div>

            {/* Confirm password field */}
            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-semibold text-foreground mb-2">
                {t('auth.register.confirmPassword')}
              </label>
              <input
                id="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  if (e.target.value) {
                    validateConfirmPassword(e.target.value);
                  } else {
                    setConfirmError('');
                  }
                }}
                onBlur={(e) => validateConfirmPassword(e.target.value)}
                className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${
                  confirmError 
                    ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                    : 'focus:ring-blue-500 dark:focus:ring-red-600'
                } focus:border-transparent transition-all duration-300`}
                placeholder="••••••••"
                disabled={isLoading}
              />
              {confirmError && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
                  <span>⚠️</span>
                  {confirmError}
                </p>
              )}
            </div>

            {/* Submit button */}
            <Button
              type="submit"
              variant="primary"
              size="lg"
              isLoading={isLoading}
              className="w-full mt-6"
            >
              {isLoading ? t('auth.register.loading') : t('auth.register.button')}
            </Button>

            {/* Login link */}
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
        </div>
      </div>
    </div>
  );
};