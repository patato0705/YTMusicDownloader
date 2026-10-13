// src/api/client.ts
/**
 * Core API client with automatic authentication.
 * All API calls go through this client.
 */

export const API_BASE = '/api';

/**
 * The access token lives in memory only (never localStorage) so an XSS bug
 * can't read it out of storage. It's lost on a hard refresh by design:
 * refreshAccessToken() below re-acquires one on app load via the httpOnly
 * refresh_token cookie, which JS never touches directly.
 */
let accessToken: string | null = null;

/**
 * Store the access token in memory after login/refresh.
 */
export function setAccessToken(token: string): void {
  accessToken = token;
}

/**
 * Clear the in-memory access token (logout, or failed refresh).
 */
export function clearAccessToken(): void {
  accessToken = null;
}

// The refresh in flight, shared by every caller: requests failing with a 401
// at the same time wait on one refresh instead of each sending their own
let refreshing: Promise<boolean> | null = null;

async function requestNewAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!res.ok) return false;

    const data = await res.json();
    if (!data.access_token) return false;

    setAccessToken(data.access_token);
    return true;
  } catch (error) {
    console.error('[Auth] Token refresh error:', error);
    return false;
  }
}

/**
 * Re-acquire an access token using the httpOnly refresh_token cookie
 * (sent automatically by the browser: credentials: 'include' is what makes
 * fetch attach it). Called on app load and on a 401.
 */
export function refreshAccessToken(): Promise<boolean> {
  if (!refreshing) {
    refreshing = requestNewAccessToken().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

/** The body of endpoints that only confirm what they did */
export interface MessageResponse {
  message: string;
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

/** A response's body: parsed JSON when it is some, else the text (null when empty) */
async function readBody(response: Response): Promise<any> {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

function send(url: string, options: RequestInit, headers: Headers): Promise<Response> {
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }
  return fetch(url, { ...options, headers, credentials: 'include' });
}

/**
 * Main fetch wrapper: authenticates the request and, on a 401, refreshes
 * the access token and retries it once.
 */
async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers = new Headers(options.headers);
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response = await send(url, options, headers);
  let data = await readBody(response);

  if (response.status === 401) {
    if (await refreshAccessToken()) {
      response = await send(url, options, headers);
      data = await readBody(response);
    } else {
      clearAccessToken();
      // Back to the sign-in page, unless already on an auth page
      const currentPath = window.location.pathname;
      if (!currentPath.startsWith('/login') && !currentPath.startsWith('/register')) {
        window.location.href = '/login';
      }
    }
  }

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
      ? `${path}?${new URLSearchParams(params).toString()}`
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
