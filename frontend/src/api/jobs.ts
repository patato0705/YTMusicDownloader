// src/api/jobs.ts
/**
 * Job queue activity
 */

import { api } from './client';

export interface JobStats {
  /** Job counts by status, plus pending_scheduled: the queued jobs waiting out a retry backoff */
  stats: Record<string, number>;
  /** In-flight jobs grouped by type, e.g. { download_track: 2, download_lyrics: 5 } */
  active_by_type: Record<string, number>;
  /** Download throttle state (backend/jobs/gate.py) */
  downloads: {
    active_workers: number;
    max_workers: number;
    /** ISO time until which all downloads are paused after a YouTube rate limit, or null */
    paused_until: string | null;
  };
}

/** What the whole queue is doing (the same for every user: the library is shared) */
export async function getJobStats(): Promise<JobStats> {
  return api.get<JobStats>('/jobs/stats/summary');
}
