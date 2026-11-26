// src/config/roles.ts
import type { Role } from '../api/auth';

/** Text colour of each role: the admin user list's role picker, and the badges below */
export const ROLE_TEXT_COLORS: Record<Role, string> = {
  administrator: 'text-purple-600 dark:text-purple-400',
  member: 'text-blue-600 dark:text-blue-400',
  visitor: 'text-slate-600 dark:text-slate-400',
};

/** Badge colours of each role, shared by the user menu and the admin user list */
export const ROLE_COLORS: Record<Role, string> = {
  administrator: `bg-purple-500/20 ${ROLE_TEXT_COLORS.administrator}`,
  member: `bg-blue-500/20 ${ROLE_TEXT_COLORS.member}`,
  visitor: `bg-slate-500/20 ${ROLE_TEXT_COLORS.visitor}`,
};
