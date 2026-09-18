// src/api/admin.ts
/**
 * Admin API endpoints
 */

import { api } from './client';
import type { User } from './auth';

// Re-export User type for convenience
export type { User } from './auth';

// ============================================================================
// TYPES
// ============================================================================

export interface CreateUserRequest {
  username: string;
  email: string;
  password: string;
  role: 'administrator' | 'member' | 'visitor';
}

export interface SettingOption {
  value: string;
  label: string;
}

export interface Setting {
  key: string;
  value: any; // Can be number, boolean, string, or object
  type: 'int' | 'bool' | 'string' | 'json';
  description: string | null;
  allowed_values: SettingOption[] | null;
  min: number | null; // lower bound for int settings
  max: number | null; // upper bound for int settings
  updated_at: string | null;
  updated_by: number | null;
}

export interface SettingUpdateRequest {
  value: any;
}

export interface MessageResponse {
  message: string;
}

export interface UserStats {
  total: number;
  active: number;
  inactive: number;
  by_role: {
    administrator: number;
    member: number;
    visitor: number;
  };
}

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
export async function updateUserRole(userId: number, role: string): Promise<User> {
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
 * Permanently delete user (admin only)
 * WARNING: This cannot be undone!
 */
export async function deleteUser(userId: number): Promise<MessageResponse> {
  return api.delete<MessageResponse>(`/admin/users/${userId}`);
}

/**
 * Get user statistics (admin only)
 */
export async function getUserStats(): Promise<UserStats> {
  return api.get<UserStats>('/admin/users/stats');
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
 * Get specific setting by key (admin only)
 */
export async function getSetting(key: string): Promise<Setting> {
  return api.get<Setting>(`/admin/settings/${key}`);
}

/**
 * Update or create a setting (admin only)
 */
export async function updateSetting(key: string, value: any): Promise<Setting> {
  return api.put<Setting>(`/admin/settings/${key}`, { value });
}

/**
 * Delete a setting (admin only)
 * Resets to default if it's a default setting
 */
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

export async function deleteSetting(key: string): Promise<MessageResponse> {
  return api.delete<MessageResponse>(`/admin/settings/${key}`);
}

// ============================================================================
// CONVENIENCE FUNCTIONS FOR TYPED SETTINGS
// ============================================================================

/**
 * Type-safe setting getters for common settings
 */
export const Settings = {
  // Scheduler
  getSyncInterval: async (): Promise<number> => {
    const setting = await getSetting('scheduler.sync_interval_hours');
    return setting.value as number;
  },
  setSyncInterval: async (hours: number): Promise<void> => {
    await updateSetting('scheduler.sync_interval_hours', hours);
  },

  getJobCleanupDays: async (): Promise<number> => {
    const setting = await getSetting('scheduler.job_cleanup_days');
    return setting.value as number;
  },
  setJobCleanupDays: async (days: number): Promise<void> => {
    await updateSetting('scheduler.job_cleanup_days', days);
  },

  // Auth
  isRegistrationEnabled: async (): Promise<boolean> => {
    const setting = await getSetting('auth.registration_enabled');
    return setting.value as boolean;
  },
  setRegistrationEnabled: async (enabled: boolean): Promise<void> => {
    await updateSetting('auth.registration_enabled', enabled);
  },

  // Download
  getMaxConcurrent: async (): Promise<number> => {
    const setting = await getSetting('download.max_concurrent');
    return setting.value as number;
  },
  setMaxConcurrent: async (count: number): Promise<void> => {
    await updateSetting('download.max_concurrent', count);
  },

  // Features
  areLyricsEnabled: async (): Promise<boolean> => {
    const setting = await getSetting('features.lyrics_enabled');
    return setting.value as boolean;
  },
  setLyricsEnabled: async (enabled: boolean): Promise<void> => {
    await updateSetting('features.lyrics_enabled', enabled);
  },

  isSyncedLyricsOnly: async (): Promise<boolean> => {
    const setting = await getSetting('features.synced_lyrics_only');
    return setting.value as boolean;
  },
  setSyncedLyricsOnly: async (enabled: boolean): Promise<void> => {
    await updateSetting('features.synced_lyrics_only', enabled);
  },

  getLyricsRetryInterval: async (): Promise<number> => {
    const setting = await getSetting('scheduler.lyrics_retry_interval_hours');
    return setting.value as number;
  },
  setLyricsRetryInterval: async (hours: number): Promise<void> => {
    await updateSetting('scheduler.lyrics_retry_interval_hours', hours);
  },

  areChartsEnabled: async (): Promise<boolean> => {
    const setting = await getSetting('features.charts_enabled');
    return setting.value as boolean;
  },
  setChartsEnabled: async (enabled: boolean): Promise<void> => {
    await updateSetting('features.charts_enabled', enabled);
  },
};