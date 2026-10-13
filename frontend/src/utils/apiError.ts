// src/utils/apiError.ts
import type { ApiError } from '../api/client';

/** Error codes the backend sends as `detail`, with their translation keys */
const CODED_ERRORS: Record<string, string> = {
  // YouTube Music couldn't be read (502): usually passes in a moment
  ytmusic_unavailable: 'common.ytmusicUnavailable',
  // A playlist that can't be read: private, or YouTube Music not answering
  playlist_unavailable: 'playlist.unavailable',
};

/**
 * A failed request's message for the user: a coded error translated, the
 * backend's message (FastAPI's 422 field errors flattened into one line),
 * otherwise `fallback` (network errors, bare HTTP statuses).
 */
export function apiErrorMessage(err: unknown, t: (key: string) => string, fallback: string): string {
  const data = (err as ApiError)?.data;
  const detail = data?.detail;

  if (typeof detail === 'string') {
    return CODED_ERRORS[detail] ? t(CODED_ERRORS[detail]) : detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((e: any) => {
      const field = e.loc?.length > 1 ? e.loc[e.loc.length - 1] : null;
      return field ? `${field}: ${e.msg}` : e.msg;
    }).join(', ');
  }
  if (typeof data?.message === 'string') return data.message;
  return fallback;
}

/**
 * The fields a 422 points at (FastAPI's validation details), for forms to
 * flag them; empty for any other error.
 */
export function invalidFields(err: unknown): Set<string> {
  const detail = (err as ApiError)?.data?.detail;
  if ((err as ApiError)?.status !== 422 || !Array.isArray(detail)) return new Set();
  return new Set(detail.map((e: any) => e.loc?.[e.loc.length - 1]).filter(Boolean));
}

/**
 * Minutes to wait before retrying, for a 429 from the failed password
 * throttling (login, change password). The backend puts the wait in seconds
 * in the body's `retry_after`, since ApiError doesn't keep response headers.
 */
export function retryAfterMinutes(err: unknown): number {
  const seconds = Number((err as ApiError)?.data?.retry_after);
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds / 60) : 1;
}
