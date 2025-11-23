// src/api/auth.ts
/**
 * Authentication API endpoints
 */

import { api, apiFetch, setAuthTokens, clearAuthTokens } from './client';

export interface User {
  id: number;
  username: string;
  email: string;
  role: 'administrator' | 'member' | 'visitor';
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface LoginResponse {
  user: User;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

/**
 * Login with username and password
 */
export async function login(username: string, password: string): Promise<LoginResponse> {
  // Don't use api.post here to avoid auth loop
  const response = await apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  // Store tokens
  setAuthTokens(response.access_token, response.refresh_token);

  return response;
}

/**
 * Register new user (admin only in production)
 */
export async function register(data: RegisterRequest): Promise<User> {
  return api.post<User>('/auth/register', data);
}

/**
 * Logout - revoke refresh token
 */
export async function logout(): Promise<void> {
  const refreshToken = localStorage.getItem('refresh_token');
  
  if (refreshToken) {
    try {
      await apiFetch('/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch (error) {
      console.error('Logout request failed:', error);
    }
  }

  clearAuthTokens();
}

/**
 * Get current user info
 */
export async function getCurrentUser(): Promise<User> {
  return api.get<User>('/auth/me');
}

/**
 * Change current user's password
 */
export async function changePassword(data: ChangePasswordRequest): Promise<void> {
  await api.post('/auth/change-password', data);
}

/**
 * List all users (admin only)
 */
export async function listUsers(includeInactive = false): Promise<User[]> {
  return api.get<User[]>('/auth/users', { include_inactive: includeInactive });
}

/**
 * Update user role (admin only)
 */
export async function updateUserRole(userId: number, role: string): Promise<User> {
  return api.patch<User>(`/auth/users/${userId}/role`, { role });
}

/**
 * Deactivate user (admin only)
 */
export async function deactivateUser(userId: number): Promise<User> {
  return api.post<User>(`/auth/users/${userId}/deactivate`);
}

/**
 * Activate user (admin only)
 */
export async function activateUser(userId: number): Promise<User> {
  return api.post<User>(`/auth/users/${userId}/activate`);
}