// src/components/ui/CreateUserModal.tsx
import React, { useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from './Button';
import { FormField, inputClass } from './FormField';
import { Modal } from './Modal';
import { ErrorBanner } from './PageStatus';
import { PasswordInput } from './PasswordInput';
import { Select } from './Select';
import * as adminApi from '../../api/admin';
import { ROLES } from '../../api/auth';
import type { Role } from '../../api/auth';
import { apiErrorMessage, invalidFields, passwordErrorKey, usernameErrorKey } from '../../utils';

interface CreateUserModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export const CreateUserModal: React.FC<CreateUserModalProps> = ({ onClose, onSuccess }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<Role>('member');
  const [error, setError] = useState('');
  const [usernameError, setUsernameError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [loading, setLoading] = useState(false);
  const { t } = useI18n();

  const keyText = (key: string | null) => (key ? t(key) : '');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const usernameProblem = keyText(usernameErrorKey(username, 'auth.errors.usernameRequired'));
    const passwordProblem = keyText(passwordErrorKey(password, 'auth.errors.passwordRequired'));
    setUsernameError(usernameProblem);
    setPasswordError(passwordProblem);
    if (usernameProblem || passwordProblem) return;

    setLoading(true);
    try {
      await adminApi.createUser({ username, password, role });
      onSuccess();
      onClose();
    } catch (err: any) {
      // The checks above mirror the backend's, so a 422 is only a safety
      // net: a translated message rather than the validator's English one
      const fields = invalidFields(err);
      if (fields.has('username') || fields.has('password')) {
        if (fields.has('username')) setUsernameError(t('auth.errors.usernameInvalid'));
        if (fields.has('password')) setPasswordError(t('auth.errors.passwordInvalid'));
      } else if (err?.status === 409 && err.data?.detail === 'username_taken') {
        setUsernameError(t('auth.errors.usernameTaken'));
      } else {
        setError(apiErrorMessage(err, t, t('common.error')));
      }
    } finally {
      setLoading(false);
    }
  };

  const dirty = Boolean(username || password);

  return (
    <Modal title={t('admin.users.create')} onClose={onClose} dismissible={!loading && !dirty}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && <ErrorBanner>{error}</ErrorBanner>}

        <FormField id="new-user-username" label={t('admin.users.username')} error={usernameError}>
          <input
            id="new-user-username"
            type="text"
            autoComplete="off"
            required
            value={username}
            onChange={(e) => {
              setUsername(e.target.value);
              setUsernameError(keyText(usernameErrorKey(e.target.value)));
            }}
            className={inputClass(usernameError)}
            disabled={loading}
          />
        </FormField>

        <FormField
          id="new-user-password"
          label={t('auth.register.password')}
          error={passwordError}
          hint={t('auth.errors.passwordTooShort')}
        >
          <PasswordInput
            id="new-user-password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setPasswordError(keyText(passwordErrorKey(e.target.value)));
            }}
            className={inputClass(passwordError)}
            disabled={loading}
          />
        </FormField>

        <div>
          <label htmlFor="new-user-role" className="block text-sm font-semibold text-foreground mb-2">
            {t('admin.users.role')}
          </label>
          <Select
            id="new-user-role"
            value={role}
            onChange={(value) => setRole(value as Role)}
            options={ROLES.map((r) => ({ value: r, label: t(`admin.users.roles.${r}`) }))}
            disabled={loading}
            className="w-full"
          />
        </div>

        <div className="flex gap-3 pt-4">
          <Button type="button" variant="ghost" onClick={onClose} disabled={loading} className="flex-1">
            {t('common.cancel')}
          </Button>
          <Button type="submit" variant="primary" isLoading={loading} className="flex-1">
            {t('admin.users.create')}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
