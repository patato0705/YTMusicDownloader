// src/contexts/JobActivityContext.tsx
/**
 * One poller for the whole app, watching the job queue.
 *
 * Pages used to each run their own timer, started from data they had already
 * fetched -- so a page could only notice a download it already knew about. A
 * download started anywhere else (another page, an artist sync, the scheduler)
 * left them polling nothing, and their badges went stale until a manual reload.
 *
 * Instead: poll the queue here, and expose `revision`, which is bumped whenever
 * the queue moves (a job queued, picked up, finished or failed). Pages refetch
 * their own data when it changes, so they react to work started anywhere.
 *
 * The cost is kept low by only polling fast while there is something to watch,
 * and not at all while the tab is in the background.
 */
import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { useAuth } from './AuthContext';
import { getJobStats } from '../api/jobs';

const ACTIVE_INTERVAL_MS = 3000;
const IDLE_INTERVAL_MS = 20000;

interface JobActivityContextType {
  /** Jobs running or waiting to run right now (drives the navbar badge) */
  activeJobCount: number;
  /** Those same jobs grouped by type, so the badge can say what they are */
  activeByType: Record<string, number>;
  /** Bumped on every change to the queue - watch it to know when to refetch */
  revision: number;
  /** Set while YouTube has rate-limited us and downloads are paused (ISO time the pause ends) */
  downloadsPausedUntil: string | null;
  /** Poll immediately, e.g. straight after queueing a download */
  refresh: () => void;
}

const JobActivityContext = createContext<JobActivityContextType | undefined>(undefined);

export const JobActivityProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  const [activeJobCount, setActiveJobCount] = useState(0);
  const [activeByType, setActiveByType] = useState<Record<string, number>>({});
  const [revision, setRevision] = useState(0);
  const [downloadsPausedUntil, setDownloadsPausedUntil] = useState<string | null>(null);

  // Kept in refs so the polling loop below never needs to be torn down and
  // rebuilt (which would restart the timer) just because a count changed.
  const activeCountRef = useRef(0);
  const signatureRef = useRef<string | null>(null);
  const refreshRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!isAuthenticated) {
      setActiveJobCount(0);
      setActiveByType({});
      setDownloadsPausedUntil(null);
      activeCountRef.current = 0;
      signatureRef.current = null;
      refreshRef.current = () => {};
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    const schedule = (delayMs: number) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(tick, delayMs);
    };

    const tick = async () => {
      if (cancelled) return;

      // Nothing to render while hidden - check back when the tab returns
      if (document.hidden) {
        schedule(IDLE_INTERVAL_MS);
        return;
      }

      try {
        const res = await getJobStats();
        if (cancelled) return;

        const stats = res?.stats || {};

        // "queued" includes jobs sitting in a retry backoff (a failed download
        // can wait anywhere from 2 minutes to 24 hours before its next attempt
        // -- see retry_delay_seconds in jobs/tasks.py). Those aren't "in
        // progress" from a user's perspective and would make the badge look
        // stuck for hours. pending_scheduled is exactly that not-yet-eligible
        // subset, so subtract it out.
        const readyToRun = (stats.queued || 0) - (stats.pending_scheduled || 0);
        let count = Math.max(0, readyToRun) + (stats.reserved || 0);
        const byType: Record<string, number> = { ...(res?.active_by_type || {}) };

        // While YouTube has us rate-limited, queued downloads are eligible
        // as far as the queue knows but no worker will touch them
        // (backend/jobs/gate.py). The red badge says why they're waiting;
        // the spinner should only reflect what's actually running.
        const pausedUntil = res?.downloads?.paused_until ?? null;
        if (pausedUntil) {
          count = Math.max(0, count - (byType.download_track || 0));
          delete byType.download_track;
        }

        activeCountRef.current = count;
        setActiveJobCount(count);
        setActiveByType(byType);
        setDownloadsPausedUntil(pausedUntil);

        // The pause is part of what pages show (tracks sitting in "new"),
        // so a change to it counts as the queue moving too.
        const signature = JSON.stringify([stats, pausedUntil]);
        if (signatureRef.current !== null && signature !== signatureRef.current) {
          setRevision((r) => r + 1);
        }
        signatureRef.current = signature;
      } catch (err) {
        console.error('Failed to fetch job stats:', err);
      }

      if (!cancelled) {
        schedule(activeCountRef.current > 0 ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS);
      }
    };

    refreshRef.current = () => {
      if (!cancelled) schedule(0);
    };

    tick();

    const onVisibilityChange = () => {
      if (!document.hidden) schedule(0);
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [isAuthenticated]);

  return (
    <JobActivityContext.Provider
      value={{ activeJobCount, activeByType, revision, downloadsPausedUntil, refresh: () => refreshRef.current() }}
    >
      {children}
    </JobActivityContext.Provider>
  );
};

export const useJobActivity = (): JobActivityContextType => {
  const context = useContext(JobActivityContext);
  if (!context) {
    throw new Error('useJobActivity must be used within JobActivityProvider');
  }
  return context;
};
