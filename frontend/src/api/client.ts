// src/api/client.ts
/**
 * Core API client with automatic authentication.
 * All API calls go through this client.
 */

const API_BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/+$/, "");

/**
 * The access token lives in memory only (never localStorage) so an XSS bug
 * can't read it out of storage. It's lost on a hard refresh by design --
 * refreshAccessToken() below re-acquires one on app load via the httpOnly
 * refresh_token cookie, which JS never touches directly.
 */
let accessToken: string | null = null;

function getAuthToken(): string | null {
  return accessToken;
}

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

/**
 * Re-acquire an access token using the httpOnly refresh_token cookie
 * (sent automatically by the browser -- credentials: 'include' below is
 * what makes fetch attach it). Called on app load and on a 401.
 */
export async function refreshAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      console.error('[Auth] Token refresh failed:', res.status, errorData);
      return false;
    }

    const data = await res.json();

    if (!data.access_token) {
      console.error('[Auth] No access_token in refresh response:', data);
      return false;
    }

    setAccessToken(data.access_token);
    return true;
  } catch (error) {
    console.error('[Auth] Token refresh error:', error);
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
    credentials: 'include',
  });

  // Parse response first (before handling 401)
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

  // Handle 401 - try refreshing token
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    
    if (refreshed) {
      // Retry with new token
      const newToken = getAuthToken();
      if (newToken) {
        headers.set('Authorization', `Bearer ${newToken}`);
        const retryResponse = await fetch(url, {
          ...options,
          headers,
          credentials: 'include',
        });
        
        // Parse retry response
        const retryContentType = retryResponse.headers.get('content-type');
        let retryData: any;
        
        if (retryContentType?.includes('application/json')) {
          retryData = await retryResponse.json();
        } else {
          const retryText = await retryResponse.text();
          try {
            retryData = retryText ? JSON.parse(retryText) : null;
          } catch {
            retryData = retryText;
          }
        }
        
        if (!retryResponse.ok) {
          const message = retryData?.detail || retryData?.message || `HTTP ${retryResponse.status}`;
          throw new ApiError(retryResponse.status, message, retryData);
        }
        
        return retryData as T;
      }
    } else {
      // Refresh failed - clear the in-memory access token
      clearAccessToken();

      // Only redirect if not already on auth pages
      const currentPath = window.location.pathname;
      if (!currentPath.startsWith('/login') && !currentPath.startsWith('/register')) {
        window.location.href = '/login';
      }
      
      // Use the actual error message from the response, not "Session expired"
      const message = data?.detail || data?.message || 'Authentication failed';
      throw new ApiError(401, message, data);
    }
  }

  // Handle errors (non-401)
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