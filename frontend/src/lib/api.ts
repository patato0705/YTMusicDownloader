// frontend/src/lib/api.ts
const API_BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/+$/, "");

/**
 * Get auth token from localStorage
 */
function getAuthToken(): string | null {
  return localStorage.getItem('access_token');
}

/**
 * Refresh access token if expired
 */
async function refreshToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) return false;

    const data = await res.json();
    localStorage.setItem('access_token', data.access_token);
    return true;
  } catch {
    return false;
  }
}

async function _fetchJson(path: string, init?: RequestInit) {
  const url = `${API_BASE}${path}`;
  
  // Add auth token to headers
  const token = getAuthToken();
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let res = await fetch(url, {
    ...init,
    headers,
  });

  // If 401, try refreshing token and retry once
  if (res.status === 401) {
    const refreshed = await refreshToken();
    if (refreshed) {
      const newToken = getAuthToken();
      if (newToken) {
        headers.set('Authorization', `Bearer ${newToken}`);
        res = await fetch(url, {
          ...init,
          headers,
        });
      }
    }
  }

  // Still 401 after refresh? Redirect to login
  if (res.status === 401) {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
    throw new Error('Session expired. Please login again.');
  }

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`API error ${res.status} ${res.statusText}: ${txt}`);
  }

  // Handle empty or non-JSON responses
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    const text = await res.text().catch(() => "");
    try {
      return text ? JSON.parse(text) : null;
    } catch {
      return text;
    }
  }
  return res.json();
}

async function apiGet(path: string) {
  return _fetchJson(path, { method: "GET" });
}

async function apiPost(path: string, body: any) {
  return _fetchJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

async function apiDelete(path: string) {
  return _fetchJson(path, { method: "DELETE" });
}

/** --- Named exports used across the frontend --- */

export async function getArtists() {
  return apiGet("/artists");
}

export async function getArtist(artistId: string) {
  return apiGet(`/artists/${encodeURIComponent(String(artistId))}`);
}

export async function getAlbum(albumId: string) {
  return apiGet(`/albums/${encodeURIComponent(String(albumId))}`);
}

export async function getTrack(videoId: string) {
  return apiGet(`/tracks/${encodeURIComponent(String(videoId))}`);
}

export async function postDownload(payload: {
  video_id: string;
  artist?: string;
  album?: string;
  title?: string;
  track_number?: number;
  year?: string;
}) {
  const qs = new URLSearchParams({ type: "download_track" });
  return apiPost(`/jobs/enqueue?${qs.toString()}`, payload);
}

export async function postAlbumDownload(albumId: string) {
  return apiPost(`/albums/${encodeURIComponent(String(albumId))}/download`, {});
}

export async function getJobStatus(jobId: string | number) {
  return apiGet(`/jobs/${encodeURIComponent(String(jobId))}`);
}

export async function importCharts(country?: string) {
  const payload = country ? { country } : {};
  const qs = new URLSearchParams({ type: "import_charts" });
  return apiPost(`/jobs/enqueue?${qs.toString()}`, payload);
}

export async function search(q: string, filter?: string, limit?: number) {
  const params = new URLSearchParams({ q: String(q) });
  if (limit !== undefined) {
    params.set("limit", String(limit));
  }
  if (filter) {
    params.set("filter", String(filter));
  }
  return apiGet(`/search?${params.toString()}`);
}

/** Default export for legacy usage */
const _defaultApi = {
  getArtists,
  getArtist,
  getAlbum,
  getTrack,
  postDownload,
  postAlbumDownload,
  getJobStatus,
  importCharts,
  search,
};

export default _defaultApi;