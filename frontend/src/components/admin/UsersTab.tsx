// src/components/admin/UsersTab.tsx
/**
 * Admin panel > Users: list, filter, create, change role, (de)activate, reset password, delete.
 */
import React, { useEffect, useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../ui/Button';
import { CreateUserModal } from '../ui/CreateUserModal';
import { SearchInput } from '../ui/SearchInput';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { TemporaryPasswordDialog } from '../ui/TemporaryPasswordDialog';
import { Select } from '../ui/Select';
import { ToggleSwitch } from '../ui/ToggleSwitch';
import { InfoTooltip } from '../ui/InfoTooltip';
import * as adminApi from '../../api/admin';
import * as authApi from '../../api/auth';
import { ROLES } from '../../api/auth';
import type { AuthConfig, Role, User } from '../../api/auth';
import { ROLE_COLORS } from '../../config/roles';
import { apiErrorMessage } from '../../utils';
import { AdminTabShell } from './AdminTabShell';
import type { AdminTabProps } from './AdminTabShell';
import { Icon } from '../ui/icons';
import { TH_CLASS } from '../ui/tableStyles';

const thClass = `px-6 ${TH_CLASS}`;

export const UsersTab: React.FC<AdminTabProps> = ({ onToast }) => {
  const { user } = useAuth();
  const { t } = useI18n();

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ userId: number; username: string } | null>(null);
  const [resetConfirm, setResetConfirm] = useState<{ userId: number; username: string } | null>(null);
  const [resetLoading, setResetLoading] = useState(false);
  const [temporaryPassword, setTemporaryPassword] = useState<{ username: string; password: string } | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [roleFilter, setRoleFilter] = useState<'all' | Role>('all');

  // Which actions apply: password accounts can't be created or reset with
  // password sign-in off, and SSO roles can't be edited when groups own them
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);

  const loadUsers = async () => {
    const usersData = await adminApi.listUsers(true); // Include inactive users
    setUsers(usersData);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [, config] = await Promise.all([loadUsers(), authApi.getAuthConfig()]);
        if (!cancelled) setAuthConfig(config);
      } catch (err: any) {
        console.error('Failed to load users:', err);
        if (!cancelled) setError(apiErrorMessage(err, t, t('common.error')));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const toggleUserStatus = async (userId: number, currentStatus: boolean) => {
    try {
      if (currentStatus) {
        await adminApi.deactivateUser(userId);
      } else {
        await adminApi.activateUser(userId);
      }
      await loadUsers();
      onToast(currentStatus ? t('admin.users.deactivated') : t('admin.users.activated'), 'success');
    } catch (err: any) {
      onToast(apiErrorMessage(err, t, t('common.error')), 'error');
    }
  };

  const changeUserRole = async (userId: number, newRole: Role) => {
    try {
      await adminApi.updateUserRole(userId, newRole);
      await loadUsers();
      onToast(t('admin.users.roleUpdated'), 'success');
    } catch (err: any) {
      onToast(apiErrorMessage(err, t, t('common.error')), 'error');
    }
  };

  const confirmReset = async () => {
    if (!resetConfirm) return;
    setResetLoading(true);
    try {
      const { temporary_password } = await adminApi.resetUserPassword(resetConfirm.userId);
      setTemporaryPassword({ username: resetConfirm.username, password: temporary_password });
    } catch (err: any) {
      onToast(apiErrorMessage(err, t, t('common.error')), 'error');
    } finally {
      setResetLoading(false);
      setResetConfirm(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteConfirm) return;
    try {
      await adminApi.deleteUser(deleteConfirm.userId);
      await loadUsers();
      onToast(t('admin.users.deleted'), 'success');
    } catch (err: any) {
      onToast(apiErrorMessage(err, t, t('common.error')), 'error');
    } finally {
      setDeleteConfirm(null);
    }
  };

  // Filter users based on search and filters
  const filteredUsers = users.filter(u => {
    const matchesSearch = searchQuery === '' ||
      u.username.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus = statusFilter === 'all' ||
      (statusFilter === 'active' && u.is_active) ||
      (statusFilter === 'inactive' && !u.is_active);

    const matchesRole = roleFilter === 'all' || u.role === roleFilter;

    return matchesSearch && matchesStatus && matchesRole;
  });

  const roleOptions = ROLES.map(role => ({ value: role, label: t(`admin.users.roles.${role}`) }));

  // Shown in the info bubble next to the "Role" column header
  const roleInfo = (
    <div className="space-y-3">
      {ROLES.map(role => (
        <div key={role}>
          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold mb-1 ${ROLE_COLORS[role]}`}>
            {t(`admin.users.roles.${role}`)}
          </span>
          <p className="text-xs leading-snug text-muted-foreground">{t(`admin.users.roleInfo.${role}`)}</p>
        </div>
      ))}
    </div>
  );

  return (
    <AdminTabShell loading={loading} error={error}>
      {showCreateModal && (
        <CreateUserModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            loadUsers();
            onToast(t('admin.users.created'), 'success');
          }}
        />
      )}

      <ConfirmDialog
        isOpen={!!deleteConfirm}
        title={t('admin.users.deleteTitle')}
        message={deleteConfirm ? t('admin.users.confirmDelete', { username: deleteConfirm.username }) : ''}
        confirmText={t('admin.users.delete')}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirm(null)}
        variant="danger"
      />

      <ConfirmDialog
        isOpen={!!resetConfirm}
        title={t('admin.users.resetPasswordTitle')}
        message={resetConfirm ? t('admin.users.confirmResetPassword', { username: resetConfirm.username }) : ''}
        confirmText={t('admin.users.resetPassword')}
        onConfirm={confirmReset}
        onCancel={() => setResetConfirm(null)}
        variant="warning"
        isLoading={resetLoading}
      />

      {temporaryPassword && (
        <TemporaryPasswordDialog
          username={temporaryPassword.username}
          password={temporaryPassword.password}
          onClose={() => setTemporaryPassword(null)}
        />
      )}

      <div className="space-y-6">
        {/* Search and Filters */}
        <div className="glass rounded-2xl p-6 space-y-4">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1">
              <SearchInput
                value={searchQuery}
                onChange={setSearchQuery}
                placeholder={t('admin.users.search')}
                showClearButton
                onClear={() => setSearchQuery('')}
              />
            </div>

            <Select
              value={statusFilter}
              onChange={(value) => setStatusFilter(value as typeof statusFilter)}
              ariaLabel={t('admin.users.status')}
              options={[
                { value: 'all', label: t('admin.users.allStatuses') },
                { value: 'active', label: t('admin.users.active') },
                { value: 'inactive', label: t('admin.users.inactive') },
              ]}
            />

            <Select
              value={roleFilter}
              onChange={(value) => setRoleFilter(value as typeof roleFilter)}
              ariaLabel={t('admin.users.role')}
              options={[
                { value: 'all', label: t('admin.users.allRoles') },
                ...roleOptions,
              ]}
            />

            {authConfig?.password_login_enabled && (
              <Button onClick={() => setShowCreateModal(true)} variant="primary">
                + {t('admin.users.create')}
              </Button>
            )}
          </div>

          <div className="text-sm text-muted-foreground">
            {t('admin.users.showing', { shown: filteredUsers.length, count: users.length })}
          </div>
        </div>

        {/* Users Table: a table from md up; on phones each row stacks into a small card */}
        <div className="glass rounded-2xl overflow-hidden">
          <div className="md:overflow-x-auto">
            <table className="w-full block md:table">
              <thead className="hidden md:table-header-group bg-slate-100/50 dark:bg-white/5 border-b border-slate-200 dark:border-white/10">
                <tr>
                  <th className={`${thClass} text-left`}>
                    {t('admin.users.username')}
                  </th>
                  <th className={`${thClass} text-left`}>
                    <span className="inline-flex items-center gap-1.5">
                      {t('admin.users.role')}
                      <InfoTooltip label={t('admin.users.roleInfo.title')} content={roleInfo} />
                    </span>
                  </th>
                  <th className={`${thClass} text-left`}>
                    {t('admin.users.status')}
                  </th>
                  <th className={`${thClass} text-right`}>
                    {t('admin.users.actions')}
                  </th>
                </tr>
              </thead>
              <tbody className="block md:table-row-group divide-y divide-slate-200 dark:divide-white/10">
                {filteredUsers.length === 0 ? (
                  <tr className="block md:table-row">
                    <td colSpan={4} className="block md:table-cell px-6 py-12 text-center">
                      <div className="text-muted-foreground">
                        <Icon name="users" className="w-8 h-8 mx-auto mb-2" />
                        <p>{t('admin.users.noResults')}</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((u) => (
                    <tr key={u.id} className="grid grid-cols-[1fr_auto] items-center gap-3 p-4 md:table-row md:p-0 hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                      <td className="md:table-cell md:px-6 md:py-4">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground">{u.username}</span>
                          {u.is_oidc && (
                            <span
                              className="px-2 py-0.5 text-xs font-medium rounded-full bg-accent-500/15 text-accent-600 dark:text-accent-400"
                              title={t('admin.users.ssoTooltip', { name: authConfig?.oidc_provider_name ?? 'SSO' })}
                            >
                              {t('admin.users.ssoBadge')}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="row-start-2 md:table-cell md:px-6 md:py-4">
                        {/* Groups own SSO roles: a change here would be undone at their next sign-in */}
                        <span title={u.is_oidc && authConfig?.oidc_roles_from_groups ? t('admin.users.roleFromGroups') : undefined}>
                          <Select
                            value={u.role}
                            onChange={(value) => changeUserRole(u.id, value as Role)}
                            options={roleOptions}
                            ariaLabel={t('admin.users.role')}
                            disabled={u.id === user?.id || (u.is_oidc && !!authConfig?.oidc_roles_from_groups)}
                            className={`text-xs font-medium ${ROLE_COLORS[u.role]} border-0 py-1`}
                          />
                        </span>
                      </td>
                      <td className="col-start-2 row-start-1 md:table-cell md:px-6 md:py-4">
                        <ToggleSwitch
                          checked={u.is_active}
                          onChange={() => toggleUserStatus(u.id, u.is_active)}
                          disabled={u.id === user?.id}
                          label={u.is_active ? t('admin.users.active') : t('admin.users.inactive')}
                        />
                      </td>
                      <td className="col-span-2 flex flex-wrap gap-2 md:table-cell md:px-6 md:py-4 md:text-right md:whitespace-nowrap md:space-x-2">
                        {/* Own password: Change Password instead (needs the current one).
                            SSO accounts have none: their sign-in is the provider's */}
                        {authConfig?.password_login_enabled && !u.is_oidc && (
                          <Button
                            onClick={() => setResetConfirm({ userId: u.id, username: u.username })}
                            variant="outline"
                            size="sm"
                            disabled={u.id === user?.id}
                          >
                            {t('admin.users.resetPassword')}
                          </Button>
                        )}
                        <Button
                          onClick={() => setDeleteConfirm({ userId: u.id, username: u.username })}
                          variant="subtleDanger"
                          size="sm"
                          disabled={u.id === user?.id}
                        >
                          {t('admin.users.delete')}
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AdminTabShell>
  );
};
