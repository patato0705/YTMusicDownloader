// src/api/auth.ts
/**
 * Authentication API endpoints
 */

import { api, setAccessToken, clearAccessToken, API_BASE } from './client';

/** Lowest to highest privilege */
export const ROLES = ['visitor', 'member', 'administrator'] as const;
export type Role = typeof ROLES[number];

export interface User {
  id: number;
  username: string;
  role: Role;
  is_active: boolean;
  /** Temporary password (first admin, admin reset): must be changed before using the app */
  must_change_password: boolean;
  /** False for single sign-on accounts (unless given one from the recovery CLI) */
  has_password: boolean;
  /** Signs in with single sign-on */
  is_oidc: boolean;
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
  password: string;
}

/** Sign-in methods offered by this deployment (GET /auth/config, public) */
export interface AuthConfig {
  password_login_enabled: boolean;
  registration_enabled: boolean;
  oidc_enabled: boolean;
  oidc_provider_name: string | null;
  /** Roles of single sign-on accounts come from provider groups (not editable here) */
  oidc_roles_from_groups: boolean;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

/**
 * Login with username and password
 */
export async function login(username: string, password: string): Promise<LoginResponse> {
  const response = await api.post<LoginResponse>('/auth/login', { username, password });

  // The refresh token is set as an httpOnly cookie by the server: only
  // the access token needs to be kept on the JS side, in memory.
  setAccessToken(response.access_token);

  return response;
}

/**
 * Create an account from the registration page (when public registration is on)
 */
export async function register(data: RegisterRequest): Promise<User> {
  return api.post<User>('/auth/register', data);
}

/**
 * Logout - revoke refresh token
 */
export async function logout(): Promise<void> {
  try {
    // No body needed: the server reads the refresh_token cookie and
    // clears both auth cookies in the response.
    await api.post('/auth/logout');
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
  // Changing the password signs out every session, this one included; the
  // response carries this session's replacement access token.
  const response = await api.post<{ access_token: string }>('/auth/change-password', data);
  setAccessToken(response.access_token);
}

/**
 * Which sign-in methods are offered (public endpoint, no auth required)
 */
export async function getAuthConfig(): Promise<AuthConfig> {
  return api.get<AuthConfig>('/auth/config');
}

/**
 * Full-page navigation to the provider (not a fetch): it redirects the
 * browser there and back to /api/auth/oidc/callback, which lands on the app.
 */
export function startSingleSignOn(): void {
  window.location.assign(`${API_BASE}/auth/oidc/login`);
}