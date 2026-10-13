// src/api/admin.ts
/**
 * Admin API endpoints
 */

import { api } from './client';
import type { MessageResponse } from './client';
import type { Role, User } from './auth';

// ============================================================================
// TYPES
// ============================================================================

export interface CreateUserRequest {
  username: string;
  password: string;
  role: Role;
}

export interface SettingOption {
  value: string;
  label: string;
}

export interface Setting {
  key: string;
  value: any; // number, boolean, string, or a Schedule, depending on the type
  type: 'int' | 'bool' | 'string' | 'schedule';
  description: string | null;
  allowed_values: SettingOption[] | null;
  min: number | null; // lower bound for int settings (and schedule intervals)
  max: number | null; // upper bound for int settings
  default: any; // built-in default value; null for keys without one
  unit?: 'hours' | 'days' | null; // schedule settings: unit of the interval
  next_run?: string | null; // schedule settings in fixed mode: ISO time of the next run
  timezone?: string | null; // schedule settings: the container's TZ
  updated_at: string | null;
  updated_by: number | null;
}

/** Value of a "schedule" setting (backend/schedules.py) */
export type Weekday = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun';
export type Schedule =
  | { mode: 'interval'; every: number }
  | { mode: 'fixed'; time: string; days: Weekday[] };

// ============================================================================
// USER MANAGEMENT
// ============================================================================

/**
 * List all users (admin only)
 */
export async function listUsers(includeInactive = false): Promise<User[]> {
  return api.get<User[]>('/admin/users', { include_inactive: includeInactive });
}

/**
 * Create a new user (admin only)
 */
export async function createUser(data: CreateUserRequest): Promise<User> {
  return api.post<User>('/admin/users', data);
}

/**
 * Update user role (admin only)
 */
export async function updateUserRole(userId: number, role: Role): Promise<User> {
  return api.patch<User>(`/admin/users/${userId}/role?role=${encodeURIComponent(role)}`);
}

/**
 * Deactivate user (admin only)
 */
export async function deactivateUser(userId: number): Promise<User> {
  return api.post<User>(`/admin/users/${userId}/deactivate`);
}

/**
 * Activate user (admin only)
 */
export async function activateUser(userId: number): Promise<User> {
  return api.post<User>(`/admin/users/${userId}/activate`);
}

/**
 * Give a user a generated temporary password (admin only, not yourself).
 * Returned once; the user must change it at next sign-in.
 */
export async function resetUserPassword(userId: number): Promise<{ temporary_password: string }> {
  return api.post<{ temporary_password: string }>(`/admin/users/${userId}/reset-password`);
}

/**
 * Permanently delete user (admin only)
 * WARNING: This cannot be undone!
 */
export async function deleteUser(userId: number): Promise<MessageResponse> {
  return api.delete<MessageResponse>(`/admin/users/${userId}`);
}

// ============================================================================
// SETTINGS MANAGEMENT
// ============================================================================

/**
 * Get all settings (admin only)
 */
export async function getAllSettings(): Promise<Setting[]> {
  return api.get<Setting[]>('/admin/settings');
}

/**
 * Change a setting (admin only); validated against its declaration
 */
export async function updateSetting(key: string, value: any): Promise<Setting> {
  return api.put<Setting>(`/admin/settings/${key}`, { value });
}

// ============================================================================
// YOUTUBE ACCOUNT COOKIES
// ============================================================================

export interface YoutubeCookiesStatus {
  present: boolean;
  cookie_count: number;
  size_bytes: number;
  modified_at: string | null;
}

/**
 * YouTube account cookies (a browser-exported cookies.txt). Only ever used
 * as a fallback for age-restricted tracks; the backend never sends the
 * cookies back, just whether a jar is there.
 */
export async function getYoutubeCookies(): Promise<YoutubeCookiesStatus> {
  return api.get<YoutubeCookiesStatus>('/admin/youtube-cookies');
}

export async function uploadYoutubeCookies(content: string): Promise<YoutubeCookiesStatus> {
  return api.put<YoutubeCookiesStatus>('/admin/youtube-cookies', { content });
}

export async function deleteYoutubeCookies(): Promise<MessageResponse> {
  return api.delete<MessageResponse>('/admin/youtube-cookies');
}
