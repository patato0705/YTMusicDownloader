// src/api/media.ts
/**
 * Media/thumbnail API endpoints
 */

import { api } from './client';

/**
 * Get local image URL (no auth required)
 * For images stored in /data directory (cover.jpg files)
 * 
 * @param imagePath - Path like "/data/kroh/BUTTERFLY/cover.jpg" or "/config/temp/covers/albumid.jpg"
 * @returns URL that can be used in <img src="">
 */
export function getLocalImageUrl(imagePath: string | null | undefined): string {
  if (!imagePath) {
    return '/assets/placeholder-music.png';
  }
  
  const VITE_API_BASE = "http://192.168.1.1:8000"
  const API_BASE = (VITE_API_BASE ?? "/api").replace(/\/+$/, "");
  
  // Clean the path - remove leading slash if present
  let cleanPath = imagePath;
  if (cleanPath.startsWith('/')) {
    cleanPath = cleanPath.substring(1);
  }
  
  // Path is already clean, just prepend API endpoint
  return `${API_BASE}/api/media/images/${cleanPath}`;
}

/**
 * Get thumbnail URL for external images (YouTube, Google, etc.)
 * Goes through proxy/cache, no auth required
 */
export function getThumbnailUrl(url: string): string {
  const VITE_API_BASE = "http://localhost:8000"
  const API_BASE = (VITE_API_BASE ?? "/api").replace(/\/+$/, "");
  return `${API_BASE}/api/media/thumbnail?url=${encodeURIComponent(url)}`;
}

/**
 * Smart image URL getter - automatically handles both local and external images
 * Use this for all image sources
 * 
 * @param imagePath - Can be local path ("/data/...") or external URL ("https://...")
 * @returns Appropriate URL for the image
 */
export function getImageUrl(imagePath: string | null | undefined): string {
  if (!imagePath) {
    return '/assets/placeholder-music.png';
  }
  
  // Check if it's an external URL (YouTube, Google, etc.)
  if (imagePath.startsWith('http://') || imagePath.startsWith('https://')) {
    // Only proxy if it's actually an external domain
    if (imagePath.includes('googleusercontent.com') || 
        imagePath.includes('ytimg.com') ||
        imagePath.includes('ggpht.com')) {
      return getThumbnailUrl(imagePath);
    }
    // If it's already pointing to our API, use it directly
    return imagePath;
  }
  
  // It's a local path like "/data/artist/album/cover.jpg"
  return getLocalImageUrl(imagePath);
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