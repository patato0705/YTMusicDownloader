// src/api/export.ts
/**
 * Export / import API.
 *
 * Exports come back as plain JSON documents; the browser download is done
 * client-side so the request goes through the normal authenticated client.
 */

import { api } from './client';

// ============================================================================
// TYPES
// ============================================================================

export interface ExportDocument {
  format_version: number;
  app_version?: string | null;
  exported_at?: string | null;
  library?: {
    artists: { id: string; name?: string | null; mode: 'light' | 'full' }[];
    albums: { id: string; title?: string | null; artist_id?: string | null; artist_name?: string | null }[];
    charts: { country_code: string; top_n_artists: number; enabled: boolean }[];
  } | null;
  catalog?: { artists: unknown[]; albums: unknown[]; tracks: unknown[] } | null;
  users?: unknown[] | null;
  settings?: unknown[] | null;
}

export interface BackupOptions {
  library: boolean;
  charts: boolean;
  catalog: boolean;
  users: boolean;
  settings: boolean;
}

export interface ImportWarning {
  code: string;
  detail: string | null;
}

export interface ImportResult {
  dry_run: boolean;
  format_version: number;
  library: {
    artists_followed: number;
    artists_existing: number;
    albums_queued: number;
    albums_existing: number;
    albums_covered_by_artist: number;
    charts_created: number;
    charts_existing: number;
    charts_skipped: number;
  } | null;
  catalog: {
    artists: number;
    albums: number;
    tracks: number;
    tracks_on_disk: number;
    tracks_to_download: number;
    albums_to_import: number;
  } | null;
  users: { created: number; skipped: string[] } | null;
  settings: { applied: number; ignored: string[] } | null;
  warnings: ImportWarning[];
}

// ============================================================================
// API
// ============================================================================

export async function exportLibrary(): Promise<ExportDocument> {
  return api.get<ExportDocument>('/export/library');
}

export async function exportBackup(options: BackupOptions): Promise<ExportDocument> {
  return api.get<ExportDocument>('/export/backup', {
    library: String(options.library),
    charts: String(options.charts),
    catalog: String(options.catalog),
    users: String(options.users),
    settings: String(options.settings),
  });
}

export async function importDocument(doc: ExportDocument, dryRun: boolean): Promise<ImportResult> {
  return api.post<ImportResult>(`/import?dry_run=${dryRun ? 'true' : 'false'}`, doc);
}

// ============================================================================
// HELPERS
// ============================================================================

/**
 * Hand a JSON document to the browser as a file download.
 */
export function downloadJson(doc: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Filename like `ytmd-library-2026-09-16.json`.
 */
export function exportFilename(kind: 'library' | 'backup'): string {
  const date = new Date().toISOString().slice(0, 10);
  return `ytmd-${kind}-${date}.json`;
}

/**
 * Parse a user-picked file into a document. Only the shape the backend will
 * validate anyway is checked here, so the error surfaced early is a plain
 * "not an export file" rather than a 422.
 */
export async function readExportFile(file: File): Promise<ExportDocument> {
  const text = await file.text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error('invalid_json');
  }
  if (
    !parsed || typeof parsed !== 'object' ||
    typeof (parsed as ExportDocument).format_version !== 'number'
  ) {
    throw new Error('not_export_file');
  }
  return parsed as ExportDocument;
}
