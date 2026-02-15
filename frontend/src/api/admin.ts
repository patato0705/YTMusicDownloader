// src/api/admin.ts
/**
 * Admin API endpoints
 */

import { api } from './client';
import type { User } from './auth';

// ============================================================================
// TYPES
// ============================================================================

export interface Setting {
  key: string;
  value: any; // Can be number, boolean, string, or object
  type: 'int' | 'bool' | 'string' | 'json';
  description: string | null;
  updated_at: string | null;
  updated_by: number | null;
}

export interface SettingUpdateRequest {
  value: any;
}

export interface MessageResponse {
  message: string;
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
 * Update user role (admin only)
 */
export async function updateUserRole(userId: number, role: string): Promise<User> {
  return api.patch<User>(`/admin/users/${userId}/role`, { role });
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

  getAudioQuality: async (): Promise<string> => {
    const setting = await getSetting('download.audio_quality');
    return setting.value as string;
  },
  setAudioQuality: async (quality: 'best' | 'high' | 'medium'): Promise<void> => {
    await updateSetting('download.audio_quality', quality);
  },

  // Features
  areLyricsEnabled: async (): Promise<boolean> => {
    const setting = await getSetting('features.lyrics_enabled');
    return setting.value as boolean;
  },
  setLyricsEnabled: async (enabled: boolean): Promise<void> => {
    await updateSetting('features.lyrics_enabled', enabled);
  },

  areChartsEnabled: async (): Promise<boolean> => {
    const setting = await getSetting('features.charts_enabled');
    return setting.value as boolean;
  },
  setChartsEnabled: async (enabled: boolean): Promise<void> => {
    await updateSetting('features.charts_enabled', enabled);
  },
};