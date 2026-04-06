// src/api/charts.ts
/**
 * Charts API endpoints
 */

import { api } from './client';

// ============================================================================
// TYPES
// ============================================================================

export interface ChartArtist {
  id: string;
  name: string;
  thumbnails: Array<{
    url: string;
    width: number;
    height: number;
  }>;
  rank: number;
  trend: 'up' | 'down' | 'neutral';
  followed: boolean;
}

export interface Chart {
  country_code: string;
  artists: ChartArtist[];
  followed: boolean;
  subscription: ChartSubscription | null;
  cached: boolean;
}

export interface ChartSubscription {
  id: number;
  country_code: string;
  enabled: boolean;
  top_n_artists: number;
  created_at: string;
  created_by: number;
  last_synced_at: string | null;
  last_error: string | null;
}

export interface FollowChartRequest {
  top_n_artists: number;
}

export interface UpdateChartRequest {
  top_n_artists?: number;
  enabled?: boolean;
}

export interface MessageResponse {
  message: string;
}

// ============================================================================
// CHART ENDPOINTS
// ============================================================================

/**
 * Get chart for a specific country
 */
export async function getChart(countryCode: string): Promise<Chart> {
  return api.get<Chart>(`/charts/${countryCode}`);
}

/**
 * List all chart subscriptions
 */
export async function listChartSubscriptions(includeDisabled = false): Promise<ChartSubscription[]> {
  return api.get<ChartSubscription[]>('/charts', { include_disabled: includeDisabled });
}

/**
 * Follow a chart (admin only)
 */
export async function followChart(countryCode: string, topNArtists: number): Promise<ChartSubscription> {
  return api.post<ChartSubscription>(`/charts/${countryCode}/follow`, { top_n_artists: topNArtists });
}

/**
 * Unfollow a chart (admin only)
 */
export async function unfollowChart(countryCode: string): Promise<MessageResponse> {
  return api.delete<MessageResponse>(`/charts/${countryCode}/follow`);
}

/**
 * Update chart subscription (admin only)
 */
export async function updateChart(
  countryCode: string,
  updates: UpdateChartRequest
): Promise<ChartSubscription> {
  return api.patch<ChartSubscription>(`/charts/${countryCode}`, updates);
}