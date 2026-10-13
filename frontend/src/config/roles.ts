// src/config/roles.ts
import type { Role } from '../api/auth';

/** Badge colours of each role, shared by the user menu and the admin user list */
export const ROLE_COLORS: Record<Role, string> = {
  administrator: 'bg-purple-500/20 text-purple-600 dark:text-purple-400',
  member: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
  visitor: 'bg-slate-500/20 text-slate-600 dark:text-slate-400',
};
