// src/utils/index.ts

/**
 * Central export file for all utility functions
 * Import utils like: import { formatDuration, formatDate } from '@/utils';
 */

// Media helpers
export {
  getBestThumbnail,
  formatArtist,
  formatAlbum,
  formatTrack,
  normalizeSearchResults,
  filterAlbums,
  categorizeAlbums,
  getPrimaryArtist,
  formatDuration,
  formatDurationLong,
  needsThumbnailProxy,
  getProxiedThumbnailUrl,
} from './mediaHelpers';

// Formatting utilities
export {
  formatDate,
  formatRelativeTime,
  formatFileSize,
  formatNumber,
  truncateText,
  capitalize,
  snakeToTitle,
  pluralize,
  formatCount,
} from './formatting';

// Validation utilities
export {
  isValidEmail,
  isValidUsername,
  validatePassword,
  passwordsMatch,
  sanitizeString,
  isEmpty,
  validateRequired,
  validateMinLength,
  validateMaxLength,
} from './validation';