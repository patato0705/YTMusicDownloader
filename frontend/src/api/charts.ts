// src/api/charts.ts
/**
 * Charts API endpoints
 */

import { api } from './client';
import type { MessageResponse } from './client';

// ============================================================================
// TYPES
// ============================================================================

export interface ChartArtist {
  id: string;
  name: string;
  thumbnail: string | null;
  rank: number;
  trend: 'up' | 'down' | 'neutral';
  followed: boolean;
}

export interface Chart {
  country_code: string;
  artists: ChartArtist[];
  followed: boolean;
  subscription: ChartSubscription | null;
}

export interface ChartSubscription {
  id: number;
  country_code: string;
  enabled: boolean;
  top_n_artists: number;
  /** Weeks out of the chart after which the artists it followed are unfollowed; null: never */
  keep_weeks: number | null;
  created_at: string;
  created_by: number;
  last_synced_at: string | null;
  last_error: string | null;
}

export interface UpdateChartRequest {
  top_n_artists?: number;
  enabled?: boolean;
  /** null: never unfollow */
  keep_weeks?: number | null;
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
export async function followChart(countryCode: string, topNArtists: number, keepWeeks: number | null): Promise<ChartSubscription> {
  return api.post<ChartSubscription>(`/charts/${countryCode}/follow`, { top_n_artists: topNArtists, keep_weeks: keepWeeks });
}

/**
 * Unfollow a chart (admin only)
 */
export async function unfollowChart(countryCode: string): Promise<MessageResponse> {
  return api.delete<MessageResponse>(`/charts/${countryCode}/follow`);
}

/**
 * Queue a sync of a followed chart right now (admin only)
 */
export async function syncChart(countryCode: string): Promise<MessageResponse> {
  return api.post<MessageResponse>(`/charts/${countryCode}/sync`);
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