// src/utils/index.ts
/**
 * Utility functions, imported from '../utils' (or '../../utils')
 */

// Media helpers
export {
  getAlbumStatus,
  getArtistStatus,
  categorizeAlbums,
  primaryArtistName,
  formatDuration,
  formatDurationLong,
  artistPath,
  albumPath,
  exceptionalStatus,
} from './mediaHelpers';

// Formatting utilities
export { formatNumber } from './formatting';

// Validation utilities
export { usernameErrorKey, passwordErrorKey, confirmErrorKey } from './validation';

// API error handling
export { apiErrorMessage, invalidFields, retryAfterMinutes } from './apiError';

// In-memory page caches
export { createMemoryCache, clearMemoryCaches } from './memoryCache';
export type { MemoryCache } from './memoryCache';
