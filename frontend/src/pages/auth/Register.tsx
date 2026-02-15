// src/pages/auth/Register.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../../components/ui/Button';

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
  
  const { login, isAuthenticated } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

  // Redirect if already logged in
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  // Validate username
  const validateUsername = (name: string) => {
    if (name && name.length < 3) {
      setUsernameError(t('auth.errors.usernameTooShort') || 'Username must be at least 3 characters');
    } else {
      setUsernameError('');
    }
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
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || t('auth.errors.registrationFailed') || 'Registration failed');
      }

      // Auto-login after registration
      await login(username, password);
      navigate('/');
    } catch (err: any) {
      // Server/API errors go to top error box
      setError(err.message || t('auth.errors.registrationFailed') || 'Registration failed');
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
                  if (emailError) setEmailError('');
                }}
                className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${
                  emailError 
                    ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                    : 'focus:ring-blue-500 dark:focus:ring-red-600'
                } focus:border-transparent transition-all duration-300`}
                placeholder="your@email.com"
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