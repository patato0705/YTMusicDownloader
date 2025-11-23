// src/utils/formatting.ts

/**
 * Formats a date string into a human-readable format
 */
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return 'Never';
  
  try {
    const date = new Date(dateString);
    
    // Check if date is valid
    if (isNaN(date.getTime())) return 'Invalid date';
    
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return 'Invalid date';
  }
}

/**
 * Formats a date string into a relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return 'Never';
  
  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    
    // Check if date is valid
    if (isNaN(date.getTime())) return 'Invalid date';
    
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffSecs < 60) return 'Just now';
    if (diffMins < 60) return `${diffMins} ${diffMins === 1 ? 'minute' : 'minutes'} ago`;
    if (diffHours < 24) return `${diffHours} ${diffHours === 1 ? 'hour' : 'hours'} ago`;
    if (diffDays < 7) return `${diffDays} ${diffDays === 1 ? 'day' : 'days'} ago`;
    if (diffDays < 30) {
      const weeks = Math.floor(diffDays / 7);
      return `${weeks} ${weeks === 1 ? 'week' : 'weeks'} ago`;
    }
    
    return formatDate(dateString);
  } catch {
    return 'Invalid date';
  }
}

/**
 * Formats a file size in bytes to human-readable format
 */
export function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes || bytes === 0) return '0 B';
  
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${units[i]}`;
}

/**
 * Formats a number with thousand separators
 */
export function formatNumber(num: number | null | undefined): string {
  if (num === null || num === undefined) return '0';
  
  return num.toLocaleString('en-US');
}

/**
 * Truncates text to a maximum length with ellipsis
 */
export function truncateText(text: string, maxLength: number): string {
  if (!text || text.length <= maxLength) return text;
  
  return text.slice(0, maxLength - 3) + '...';
}

/**
 * Capitalizes the first letter of a string
 */
export function capitalize(text: string): string {
  if (!text) return '';
  
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

/**
 * Converts a snake_case string to Title Case
 */
export function snakeToTitle(text: string): string {
  if (!text) return '';
  
  return text
    .split('_')
    .map(word => capitalize(word))
    .join(' ');
}

/**
 * Pluralizes a word based on count
 */
export function pluralize(word: string, count: number): string {
  if (count === 1) return word;
  
  // Simple pluralization rules
  if (word.endsWith('y')) {
    return word.slice(0, -1) + 'ies';
  }
  if (word.endsWith('s') || word.endsWith('x') || word.endsWith('ch') || word.endsWith('sh')) {
    return word + 'es';
  }
  
  return word + 's';
}

/**
 * Formats a count with its plural word (e.g., "3 albums")
 */
export function formatCount(count: number, word: string): string {
  return `${formatNumber(count)} ${pluralize(word, count)}`;
}