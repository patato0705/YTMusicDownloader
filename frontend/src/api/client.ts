// src/api/client.ts
/**
 * Core API client with automatic authentication.
 * All API calls go through this client.
 */

const API_BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/+$/, "");

/**
 * Get auth token from localStorage
 */
function getAuthToken(): string | null {
  return localStorage.getItem('access_token');
}

/**
 * Set auth tokens in localStorage
 */
export function setAuthTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem('access_token', accessToken);
  localStorage.setItem('refresh_token', refreshToken);
}

/**
 * Clear auth tokens from localStorage
 */
export function clearAuthTokens(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

/**
 * Refresh access token using refresh token
 */
async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) return false;

    const data = await res.json();
    localStorage.setItem('access_token', data.access_token);
    return true;
  } catch {
    return false;
  }
}

/**
 * API Error class with status code
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public data?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Main fetch wrapper with auth and retry logic
 */
export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  
  // Add auth token to headers
  const token = getAuthToken();
  const headers = new Headers(options.headers);
  
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  
  // Add Content-Type for requests with body
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response = await fetch(url, {
    ...options,
    headers,
  });

  // Handle 401 - try refreshing token
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    
    if (refreshed) {
      // Retry with new token
      const newToken = getAuthToken();
      if (newToken) {
        headers.set('Authorization', `Bearer ${newToken}`);
        response = await fetch(url, {
          ...options,
          headers,
        });
      }
    } else {
      // Refresh failed - redirect to login
      clearAuthTokens();
      window.location.href = '/login';
      throw new ApiError(401, 'Session expired');
    }
  }

  // Parse response
  const contentType = response.headers.get('content-type');
  let data: any;

  if (contentType?.includes('application/json')) {
    data = await response.json();
  } else {
    const text = await response.text();
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }
  }

  // Handle errors
  if (!response.ok) {
    const message = data?.detail || data?.message || `HTTP ${response.status}`;
    throw new ApiError(response.status, message, data);
  }

  return data as T;
}

/**
 * Convenience methods
 */
export const api = {
  get: <T = any>(path: string, params?: Record<string, any>): Promise<T> => {
    const url = params
      ? `${path}?${new URLSearchParams(params as any).toString()}`
      : path;
    return apiFetch<T>(url, { method: 'GET' });
  },

  post: <T = any>(path: string, body?: any): Promise<T> => {
    return apiFetch<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  put: <T = any>(path: string, body?: any): Promise<T> => {
    return apiFetch<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  patch: <T = any>(path: string, body?: any): Promise<T> => {
    return apiFetch<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  delete: <T = any>(path: string): Promise<T> => {
    return apiFetch<T>(path, { method: 'DELETE' });
  },
};