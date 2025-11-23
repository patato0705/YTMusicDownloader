// src/api/jobs.ts
/**
 * Job queue API endpoints
 */

import { api } from './client';

export interface Job {
  id: number;
  type: string;
  status: string;
  payload?: any;
  attempts?: number;
  max_attempts?: number;
  priority?: number;
  scheduled_at?: string;
  started_at?: string;
  finished_at?: string;
  created_at?: string;
  last_error?: string;
  result?: any;
  user_id?: number;
}

export interface EnqueueJobRequest {
  type: string;
  payload?: any;
  scheduled_at?: string;
  priority?: number;
  max_attempts?: number;
}

export interface EnqueueJobResponse {
  ok: boolean;
  job_id: number;
  message?: string;
}

export interface JobStats {
  ok: boolean;
  stats: Record<string, number>;
  total: number;
}

/**
 * Enqueue a new job
 */
export async function enqueueJob(request: EnqueueJobRequest): Promise<EnqueueJobResponse> {
  return api.post<EnqueueJobResponse>('/jobs/enqueue', request);
}

/**
 * List jobs with optional filtering
 */
export async function listJobs(
  status?: string,
  limit = 100
): Promise<Job[]> {
  const params: Record<string, any> = { limit };
  if (status) params.status = status;
  
  return api.get<Job[]>('/jobs', params);
}

/**
 * Get single job by ID
 */
export async function getJob(jobId: number): Promise<Job> {
  return api.get<Job>(`/jobs/${jobId}`);
}

/**
 * Cancel a job
 */
export async function cancelJob(jobId: number, message?: string): Promise<any> {
  return api.post(`/jobs/${jobId}/cancel`, { message });
}

/**
 * Requeue a failed job (admin only)
 */
export async function requeueJob(jobId: number, delaySeconds?: number): Promise<any> {
  return api.post(`/jobs/${jobId}/requeue`, { delay_seconds: delaySeconds });
}

/**
 * Get job statistics
 */
export async function getJobStats(): Promise<JobStats> {
  return api.get<JobStats>('/jobs/stats/summary');
}

/**
 * Poll job until completion or failure
 * 
 * @param jobId - Job ID to poll
 * @param onUpdate - Callback for status updates
 * @param interval - Polling interval in ms (default 2000)
 * @param timeout - Max polling time in ms (default 5 minutes)
 */
export async function pollJob(
  jobId: number,
  onUpdate?: (job: Job) => void,
  interval = 2000,
  timeout = 300000
): Promise<Job> {
  const startTime = Date.now();

  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const job = await getJob(jobId);
        
        if (onUpdate) {
          onUpdate(job);
        }

        // Check if job is finished
        if (job.status === 'done') {
          resolve(job);
          return;
        }

        if (job.status === 'failed') {
          reject(new Error(job.last_error || 'Job failed'));
          return;
        }

        // Check timeout
        if (Date.now() - startTime > timeout) {
          reject(new Error('Job polling timeout'));
          return;
        }

        // Continue polling
        setTimeout(poll, interval);
      } catch (error) {
        reject(error);
      }
    };

    poll();
  });
}