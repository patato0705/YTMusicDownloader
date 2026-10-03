// src/utils/index.ts

/**
 * Central export file for all utility functions
 * Import utils like: import { formatDuration, formatDate } from '@/utils';
 */

// Media helpers
export {
  formatArtist,
  formatAlbum,
  formatTrack,
  normalizeSearchResults,
  filterAlbums,
  categorizeAlbums,
  getAlbumStatus,
  getArtistStatus,
  getPrimaryArtist,
  formatDuration,
  formatDurationLong,
} from './mediaHelpers';

// Formatting utilities
export { formatNumber } from './formatting';

// Validation utilities
export { getUsernameError, getPasswordError } from './validation';
export type { UsernameError, PasswordError } from './validation';

// API error parsing
export { parseApiError, retryAfterMinutes } from './apiError';