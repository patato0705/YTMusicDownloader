// src/components/admin/CreateUserModal.tsx
import React, { useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../ui/Button';
import * as adminApi from '../../api/admin';

interface CreateUserModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export const CreateUserModal: React.FC<CreateUserModalProps> = ({ onClose, onSuccess }) => {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'member' | 'visitor' | 'administrator'>('member');
  const [error, setError] = useState('');
  const [usernameError, setUsernameError] = useState('');
  const [emailError, setEmailError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [loading, setLoading] = useState(false);
  const { t } = useI18n();

  // Parse API validation errors from ApiError (client.ts)
  // err.message = stringified detail (may be [object Object] if detail was an array)
  // err.data    = full raw response body
  // err.status  = HTTP status code
  const parseApiError = (err: any): string => {
    const data = err.data;

    // FastAPI validation error: { detail: [{loc, msg, type}, ...] }
    if (data?.detail && Array.isArray(data.detail)) {
      return data.detail.map((e: any) => {
        const field = e.loc && e.loc.length > 1 ? e.loc[e.loc.length - 1] : null;
        const msg = e.msg || 'Invalid value';
        return field ? `${field}: ${msg}` : msg;
      }).join(', ');
    }

    // FastAPI simple string detail: { detail: "some error" }
    if (data?.detail && typeof data.detail === 'string') {
      return data.detail;
    }

    // Fallback to err.message (already a string from ApiError constructor)
    return err.message || 'An error occurred';
  };

  // Validate username
  const validateUsername = (value: string) => {
    if (value && value.length < 3) {
      setUsernameError(t('auth.errors.usernameTooShort') || 'Username must be at least 3 characters');
    } else if (value && value.length > 64) {
      setUsernameError(t('auth.errors.usernameTooLong') || 'Username must be at most 64 characters');
    } else {
      setUsernameError('');
    }
  };

  // Validate email
  const validateEmail = (value: string) => {
    if (value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      setEmailError(t('auth.errors.invalidEmail') || 'Please enter a valid email address');
    } else {
      setEmailError('');
    }
  };

  // Validate password
  const validatePassword = (value: string) => {
    if (value && value.length < 8) {
      setPasswordError(t('auth.errors.passwordTooShort'));
    } else {
      setPasswordError('');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setUsernameError('');
    setEmailError('');
    setPasswordError('');

    // Validate all fields
    if (!username) {
      setUsernameError(t('auth.errors.usernameRequired') || 'Username is required');
      return;
    }
    if (username.length < 3) {
      setUsernameError(t('auth.errors.usernameTooShort') || 'Username must be at least 3 characters');
      return;
    }
    if (username.length > 64) {
      setUsernameError(t('auth.errors.usernameTooLong') || 'Username must be at most 64 characters');
      return;
    }

    if (!email) {
      setEmailError(t('auth.errors.emailRequired') || 'Email is required');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setEmailError(t('auth.errors.invalidEmail') || 'Please enter a valid email address');
      return;
    }

    if (!password) {
      setPasswordError(t('auth.errors.passwordRequired') || 'Password is required');
      return;
    }
    if (password.length < 8) {
      setPasswordError(t('auth.errors.passwordTooShort'));
      return;
    }

    setLoading(true);

    try {
      await adminApi.createUser({
        username,
        email,
        password,
        role,
      });

      onSuccess();
      onClose();
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
        // If no field matched, show as generic error
        if (!hasFieldError) {
          setError(parseApiError(err));
        }
      } else {
        setError(parseApiError(err));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="glass rounded-3xl p-8 max-w-md w-full border-gradient shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gradient">
            {t('admin.users.create')}
          </h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors text-xl"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          {error && (
            <div className="bg-red-500/10 dark:bg-red-500/5 rounded-xl p-3 border border-red-500/20">
              <p className="text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
                <span>⚠️</span> {error}
              </p>
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-foreground mb-2">
              {t('admin.users.username')}
            </label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                if (e.target.value) validateUsername(e.target.value);
                else setUsernameError('');
              }}
              onBlur={(e) => validateUsername(e.target.value)}
              className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground focus:outline-none focus:ring-2 ${
                usernameError 
                  ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                  : 'focus:ring-blue-500 dark:focus:ring-red-600'
              } transition-all`}
              disabled={loading}
            />
            {usernameError && (
              <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
                <span>⚠️</span> {usernameError}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-semibold text-foreground mb-2">
              {t('admin.users.email')}
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (e.target.value) validateEmail(e.target.value);
                else setEmailError('');
              }}
              onBlur={(e) => validateEmail(e.target.value)}
              className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground focus:outline-none focus:ring-2 ${
                emailError 
                  ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                  : 'focus:ring-blue-500 dark:focus:ring-red-600'
              } transition-all`}
              disabled={loading}
            />
            {emailError && (
              <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
                <span>⚠️</span> {emailError}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-semibold text-foreground mb-2">
              {t('auth.register.password')}
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (e.target.value) validatePassword(e.target.value);
                else setPasswordError('');
              }}
              onBlur={(e) => validatePassword(e.target.value)}
              className={`w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground focus:outline-none focus:ring-2 ${
                passwordError 
                  ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50' 
                  : 'focus:ring-blue-500 dark:focus:ring-red-600'
              } transition-all`}
              disabled={loading}
            />
            {passwordError ? (
              <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
                <span>⚠️</span> {passwordError}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground mt-1.5">
                {t('auth.errors.passwordTooShort')}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-semibold text-foreground mb-2">
              {t('admin.users.role')}
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as any)}
              className="w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground bg-white dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 transition-all appearance-none cursor-pointer"
              disabled={loading}
              style={{
                backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                backgroundPosition: 'right 0.5rem center',
                backgroundRepeat: 'no-repeat',
                backgroundSize: '1.5em 1.5em',
                paddingRight: '2.5rem'
              }}
            >
              <option value="visitor">Visitor</option>
              <option value="member">Member</option>
              <option value="administrator">Administrator</option>
            </select>
          </div>

          <div className="flex gap-3 pt-4">
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={loading}
              className="flex-1"
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={loading}
              className="flex-1"
            >
              {t('admin.users.create')}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};