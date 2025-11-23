// src/pages/auth/Login.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import * as authApi from '../../api/auth';

export const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
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
    setIsLoading(true);

    try {
      await login(username, password);
      
      // Check if default admin with default password
      const user = await authApi.getCurrentUser();
      
      if (user.id === 1 && password === 'default') {
        navigate('/change-password', { 
          state: { 
            forced: true, 
            message: t('auth.changePassword.defaultWarning') || 'Please change the default password'
          } 
        });
      } else {
        navigate('/');
      }
    } catch (err: any) {
      setError(err.message || t('auth.errors.invalidCredentials'));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-secondary px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h2 className="text-4xl font-bold text-foreground mb-2">
            {t('auth.login.title')}
          </h2>
          <p className="text-muted-foreground">{t('auth.login.subtitle')}</p>
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
                {t('auth.login.username')}
              </label>
              <input
                id="username"
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-3 bg-background border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
                placeholder={t('auth.login.username')}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-card-foreground mb-2">
                {t('auth.login.password')}
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 bg-background border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent transition"
                placeholder={t('auth.login.password')}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 px-4 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-lg transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background"
          >
            {isLoading ? t('auth.login.loading') : t('auth.login.button')}
          </button>

          <div className="text-center text-sm text-muted-foreground">
            {t('auth.login.noAccount')}{' '}
            <Link to="/register" className="text-primary hover:text-primary/80 font-medium">
              {t('auth.login.register')}
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
};