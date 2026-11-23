// src/api/media.ts
/**
 * Image URLs. Both endpoints require auth, carried by the access_token cookie
 * the browser attaches to the <img> request.
 */

import { API_BASE } from './client';

// Hosts the backend's thumbnail proxy fetches from (routers/media.py).
// Images from any other host are refused by the pages' Content-Security-Policy.
const PROXIED_HOSTS = ['googleusercontent.com', 'ytimg.com', 'ggpht.com', 'gstatic.com'];

/**
 * URL for an <img> showing an image: a file saved on disk ("/data/...",
 * "/config/covers/..."), or a YouTube Music thumbnail, served through the
 * backend's caching proxy. '' when there's none (Artwork then draws its fallback).
 */
export function getImageUrl(imagePath: string | null | undefined): string {
  if (!imagePath) return '';

  if (/^https?:\/\//.test(imagePath)) {
    let host = '';
    try {
      host = new URL(imagePath).hostname;
    } catch {
      // Not a URL after all: shown as is, and Artwork falls back if it fails
    }
    const proxied = PROXIED_HOSTS.some((domain) => host === domain || host.endsWith(`.${domain}`));
    return proxied ? `${API_BASE}/media/thumbnail?url=${encodeURIComponent(imagePath)}` : imagePath;
  }

  return `${API_BASE}/media/images/${imagePath.replace(/^\/+/, '')}`;
}
