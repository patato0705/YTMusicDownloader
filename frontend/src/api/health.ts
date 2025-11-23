// src/api/health.ts
/**
 * Health check API endpoint
 */

import { api } from './client';

export interface HealthStatus {
  status: string;
  database?: boolean;
  ytmusic?: boolean;
  binaries?: Record<string, boolean>;
  filesystem?: boolean;
  [key: string]: any;
}

/**
 * Health check endpoint
 * 
 * @param deep - If true, perform deeper checks (YTMusic network call)
 * 
 * Shallow checks (default):
 * - DB connectivity
 * - Presence of required binaries
 * - FS permissions
 * - YTMusic client init
 * 
 * Deep checks (deep=true):
 * - Attempt a lightweight YTMusic call
 */
export async function checkHealth(deep = false): Promise<HealthStatus> {
  return api.get<HealthStatus>('/health', { deep });
}