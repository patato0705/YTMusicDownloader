// src/pages/auth/Register.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';

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
      // Note: Register endpoint requires admin auth in production
      // This might fail - handle accordingly
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Registration failed');
      }

      // Auto-login after registration
      await login(username, password);
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Registration failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-secondary px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h2 className="text-4xl font-bold text-foreground mb-2">
            {t('auth.register.title')}
          </h2>
          <p className="text-muted-foreground">{t('auth.register.subtitle')}</p>
        </div>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6 bg-card p-8 rounded-xl shadow-2xl border border-border">
          {error && (
            <div className="bg-red-500/10 border border-red-500 text-red-500 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-card-foreground mb-2">
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
                className="w-full px-4 py-3 bg-background border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
                placeholder={t('auth.register.username')}
              />
              <p className="text-xs text-muted-foreground mt-1">3-64 characters</p>
            </div>

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-card-foreground mb-2">
                {t('auth.register.email')}
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 bg-background border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
                placeholder="your@email.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-card-foreground mb-2">
                {t('auth.register.password')}
              </label>
              <input
                id="password"
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 bg-background border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
                placeholder={t('auth.register.password')}
              />
              <p className="text-xs text-muted-foreground mt-1">
                {t('auth.errors.passwordTooShort')}
              </p>
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-card-foreground mb-2">
                {t('auth.register.confirmPassword')}
              </label>
              <input
                id="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-4 py-3 bg-background border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
                placeholder={t('auth.register.confirmPassword')}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 px-4 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-lg transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background"
          >
            {isLoading ? t('auth.register.loading') : t('auth.register.button')}
          </button>

          <div className="text-center text-sm text-muted-foreground">
            {t('auth.register.hasAccount')}{' '}
            <Link to="/login" className="text-primary hover:text-primary/80 font-medium">
              {t('auth.register.login')}
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
};