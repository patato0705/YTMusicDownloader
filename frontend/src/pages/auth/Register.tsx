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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Validation
    if (username.length < 3) {
      setError(t('auth.errors.usernameTooShort') || 'Username must be at least 3 characters');
      return;
    }

    if (password.length < 8) {
      setError(t('auth.errors.passwordTooShort'));
      return;
    }

    if (password !== confirmPassword) {
      setError(t('auth.errors.passwordMismatch'));
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

            {/* Username field */}
            <div>
              <label htmlFor="username" className="block text-sm font-semibold text-foreground mb-2">
                {t('auth.register.username')}
              </label>
              <input
                id="username"
                type="text"
                required
                minLength={3}
                maxLength={64}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 focus:border-transparent transition-all duration-300"
                placeholder={t('auth.register.username')}
                disabled={isLoading}
              />
              <p className="text-xs text-muted-foreground mt-1.5">
                {t('auth.register.usernameHint') || '3-64 characters'}
              </p>
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
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 focus:border-transparent transition-all duration-300"
                placeholder="your@email.com"
                disabled={isLoading}
              />
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
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
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
                {t('auth.register.confirmPassword')}
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