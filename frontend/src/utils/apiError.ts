// src/utils/apiError.ts
import type { ApiError } from '../api/client';

/**
 * Parse an ApiError thrown by the API client (see src/api/client.ts) into a
 * user-facing message.
 *
 * FastAPI validation errors (422) return `detail` as an array of field-level
 * errors on `err.data.detail` — this flattens them into a single readable
 * string (e.g. "username: field required, password: field required").
 * A plain string `detail` is returned as-is, and anything else falls back to
 * `err.message`, or the caller-supplied `fallback` if that's also missing.
 */
export function parseApiError(err: any, fallback: string = 'An error occurred'): string {
  const data = (err as ApiError)?.data;

  if (data?.detail && Array.isArray(data.detail)) {
    return data.detail.map((e: any) => {
      const field = e.loc && e.loc.length > 1 ? e.loc[e.loc.length - 1] : null;
      const msg = e.msg || 'Invalid value';
      return field ? `${field}: ${msg}` : msg;
    }).join(', ');
  }

  if (data?.detail && typeof data.detail === 'string') {
    return data.detail;
  }

  return err?.message || fallback;
}

/**
 * Minutes to wait before retrying, for a 429 from the failed password
 * throttling (login, change password). The backend puts the wait in seconds
 * in the body's `retry_after`, since ApiError doesn't keep response headers.
 */
export function retryAfterMinutes(err: any): number {
  const seconds = Number((err as ApiError)?.data?.retry_after);
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds / 60) : 1;
}
