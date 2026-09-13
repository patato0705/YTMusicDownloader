// src/api/auth.ts
/**
 * Authentication API endpoints
 */

import { api, apiFetch, setAccessToken, clearAccessToken } from './client';

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

  // The refresh token is set as an httpOnly cookie by the server -- only
  // the access token needs to be kept on the JS side, in memory.
  setAccessToken(response.access_token);

  return response;
}

/**
 * Register new user (admin only)
 */
export async function register(data: RegisterRequest): Promise<User> {
  return api.post<User>('/auth/register', data);
}

/**
 * Logout - revoke refresh token
 */
export async function logout(): Promise<void> {
  try {
    // No body needed -- the server reads the refresh_token cookie and
    // clears both auth cookies in the response.
    await apiFetch('/auth/logout', { method: 'POST' });
  } catch (error) {
    console.error('Logout request failed:', error);
  }

  clearAccessToken();
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
 * Check if public registration is enabled (public endpoint, no auth required)
 */
export async function isRegistrationEnabled(): Promise<boolean> {
  try {
    // Use apiFetch directly to bypass auth headers for this public endpoint
    const response = await apiFetch<{ enabled: boolean }>('/auth/registration-status', {
      method: 'GET',
    });
    return response.enabled;
  } catch (err) {
    // If endpoint fails, assume enabled (fail-open) - backend will validate on submit
    console.error('Failed to check registration status:', err);
    return true;
  }
}