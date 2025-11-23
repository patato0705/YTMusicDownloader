// src/api/media.ts
/**
 * Media/thumbnail API endpoints
 */

import { api, apiFetch } from './client';

/**
 * Get thumbnail image (proxied and cached)
 * No authentication required - thumbnails are public
 * 
 * Flow:
 * 1. Check memory cache
 * 2. Check disk cache
 * 3. Fetch from source and cache
 */
export async function getThumbnail(url: string): Promise<Blob> {
  const response = await apiFetch(`/media/thumbnail?url=${encodeURIComponent(url)}`, {
    method: 'GET',
  });
  
  // If response is already a Blob, return it
  if (response instanceof Blob) {
    return response;
  }
  
  // Otherwise, it might be a JSON error or we need to fetch as blob
  throw new Error('Invalid thumbnail response');
}

/**
 * Get thumbnail URL for use in img src
 * Returns a proxied URL that goes through the cache
 */
export function getThumbnailUrl(url: string): string {
  const API_BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/+$/, "");
  return `${API_BASE}/media/thumbnail?url=${encodeURIComponent(url)}`;
}

/**
 * Get cache debug info (admin only)
 */
export async function getThumbnailDebugInfo(): Promise<any> {
  return api.get('/media/thumbnail/debug');
}

/**
 * Clear thumbnail cache (admin only)
 */
export async function clearThumbnailCache(): Promise<any> {
  return api.delete('/media/cache/clear');
}