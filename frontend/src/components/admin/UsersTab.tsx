// src/components/admin/UsersTab.tsx
/**
 * Admin panel > Users: list, filter, create, change role, (de)activate, delete.
 */
import React, { useEffect, useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../ui/Button';
import { CreateUserModal } from '../ui/CreateUserModal';
import { SearchInput } from '../ui/SearchInput';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { Select } from '../ui/Select';
import { ToggleSwitch } from '../ui/ToggleSwitch';
import { InfoTooltip } from '../ui/InfoTooltip';
import * as adminApi from '../../api/admin';
import type { User } from '../../api/admin';
import { parseApiError } from '../../utils';
import { AdminTabShell } from './AdminTabShell';
import type { AdminTabProps } from './AdminTabShell';

type Role = User['role'];

// Lowest to highest privilege
const ROLES: Role[] = ['visitor', 'member', 'administrator'];

const roleColors: Record<Role, string> = {
  administrator: 'bg-purple-500/20 text-purple-600 dark:text-purple-400',
  member: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
  visitor: 'bg-slate-500/20 text-slate-600 dark:text-slate-400',
};

export const UsersTab: React.FC<AdminTabProps> = ({ onToast }) => {
  const { user } = useAuth();
  const { t } = useI18n();

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ userId: number; username: string } | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [roleFilter, setRoleFilter] = useState<'all' | Role>('all');

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
        await loadUsers();
      } catch (err: any) {
        console.error('Failed to load users:', err);
        if (!cancelled) setError(parseApiError(err, 'Failed to load data'));
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
      onToast(parseApiError(err), 'error');
    }
  };

  const changeUserRole = async (userId: number, newRole: string) => {
    try {
      await adminApi.updateUserRole(userId, newRole);
      await loadUsers();
      onToast(t('admin.users.roleUpdated'), 'success');
    } catch (err: any) {
      onToast(parseApiError(err), 'error');
    }
  };

  const confirmDelete = async () => {
    if (!deleteConfirm) return;
    try {
      await adminApi.deleteUser(deleteConfirm.userId);
      await loadUsers();
      onToast(t('admin.users.deleted'), 'success');
    } catch (err: any) {
      onToast(parseApiError(err), 'error');
    } finally {
      setDeleteConfirm(null);
    }
  };

  // Filter users based on search and filters
  const filteredUsers = users.filter(u => {
    const matchesSearch = searchQuery === '' ||
      u.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email.toLowerCase().includes(searchQuery.toLowerCase());

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
          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold mb-1 ${roleColors[role]}`}>
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
        cancelText={t('common.cancel')}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirm(null)}
        variant="danger"
      />

      <div className="space-y-6">
        {/* Search and Filters */}
        <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10 space-y-4">
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
              onChange={(value) => setStatusFilter(value as any)}
              options={[
                { value: 'all', label: t('admin.users.allStatuses') },
                { value: 'active', label: t('admin.users.active') },
                { value: 'inactive', label: t('admin.users.inactive') },
              ]}
            />

            <Select
              value={roleFilter}
              onChange={(value) => setRoleFilter(value as any)}
              options={[
                { value: 'all', label: t('admin.users.allRoles') },
                ...roleOptions,
              ]}
            />

            <Button onClick={() => setShowCreateModal(true)} variant="primary">
              + {t('admin.users.create')}
            </Button>
          </div>

          <div className="text-sm text-muted-foreground">
            {t('admin.users.showing')} {filteredUsers.length} {t('admin.users.of')} {users.length} {t('admin.users.users')}
          </div>
        </div>

        {/* Users Table */}
        <div className="glass rounded-2xl overflow-hidden border border-slate-200/50 dark:border-white/10">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-100/50 dark:bg-white/5 border-b border-slate-200 dark:border-white/10">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {t('admin.users.username')}
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {t('admin.users.email')}
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    <span className="inline-flex items-center gap-1.5">
                      {t('admin.users.role')}
                      <InfoTooltip label={t('admin.users.roleInfo.title')} content={roleInfo} />
                    </span>
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {t('admin.users.status')}
                  </th>
                  <th className="px-6 py-4 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {t('admin.users.actions')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-white/10">
                {filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center">
                      <div className="text-muted-foreground">
                        <span className="text-4xl mb-2 block">👥</span>
                        <p>{t('admin.users.noResults')}</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-semibold text-foreground">{u.username}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm text-muted-foreground">{u.email}</div>
                      </td>
                      <td className="px-6 py-4">
                        <Select
                          value={u.role}
                          onChange={(value) => changeUserRole(u.id, value)}
                          options={roleOptions}
                          disabled={u.id === user?.id}
                          className={`text-xs font-medium ${roleColors[u.role]} border-0 py-1`}
                        />
                      </td>
                      <td className="px-6 py-4">
                        <ToggleSwitch
                          checked={u.is_active}
                          onChange={() => toggleUserStatus(u.id, u.is_active)}
                          disabled={u.id === user?.id}
                          label={u.is_active ? t('admin.users.active') : t('admin.users.inactive')}
                        />
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Button
                          onClick={() => setDeleteConfirm({ userId: u.id, username: u.username })}
                          variant="danger"
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
