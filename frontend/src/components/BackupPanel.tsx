// src/components/BackupPanel.tsx
/**
 * Admin panel > Backup tab: download a full backup, or import an export file
 * (library manifest or backup). Importing always previews first via a dry
 * run; the numbers shown are exactly what the confirmed run will do.
 */
import React, { useRef, useState } from 'react';
import { useI18n } from '../contexts/I18nContext';
import { Button } from './ui/Button';
import { SectionHeader } from './ui/SectionHeader';
import { ToggleSwitch } from './ui/ToggleSwitch';
import {
  exportBackup,
  importDocument,
  downloadJson,
  exportFilename,
  readExportFile,
} from '../api/export';
import type { BackupOptions, ExportDocument, ImportResult } from '../api/export';
import { parseApiError } from '../utils';

interface BackupPanelProps {
  onToast: (message: string, type: 'success' | 'error') => void;
}

export const BackupPanel: React.FC<BackupPanelProps> = ({ onToast }) => {
  const { t } = useI18n();

  // Export
  const [options, setOptions] = useState<BackupOptions>({ library: true, charts: true, catalog: true, users: true, settings: true });
  const [exporting, setExporting] = useState(false);

  // Import
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [doc, setDoc] = useState<ExportDocument | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);

  const handleExport = async () => {
    setExporting(true);
    try {
      downloadJson(await exportBackup(options), exportFilename('backup'));
    } catch (err: any) {
      console.error('Failed to export backup:', err);
      onToast(parseApiError(err, t('admin.backup.export.failed')), 'error');
    } finally {
      setExporting(false);
    }
  };

  const resetImport = () => {
    setFileName(null);
    setDoc(null);
    setPreview(null);
    setResult(null);
    setImportError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setFileName(file.name);
    setDoc(null);
    setPreview(null);
    setResult(null);
    setImportError(null);
    setPreviewLoading(true);

    try {
      const parsed = await readExportFile(file);
      setDoc(parsed);
      setPreview(await importDocument(parsed, true));
    } catch (err: any) {
      console.error('Failed to preview import:', err);
      const code = err?.message;
      setImportError(
        code === 'invalid_json' || code === 'not_export_file'
          ? t(`admin.backup.import.errors.${code}`)
          : parseApiError(err, t('admin.backup.import.failed'))
      );
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleApply = async () => {
    if (!doc) return;
    setApplying(true);
    try {
      const applied = await importDocument(doc, false);
      setResult(applied);
      onToast(t('admin.backup.import.done'), 'success');
    } catch (err: any) {
      console.error('Failed to apply import:', err);
      setImportError(parseApiError(err, t('admin.backup.import.failed')));
    } finally {
      setApplying(false);
    }
  };

  // Which of the document's sections the file carries, for the preview header
  const sectionsOf = (d: ExportDocument): string[] =>
    (['library', 'catalog', 'users', 'settings'] as const)
      .filter(key => d[key] != null)
      .map(key => t(`admin.backup.sections.${key}`));

  const summary = result ?? preview;

  const renderSummary = (r: ImportResult) => {
    const rows: { label: string; value: React.ReactNode }[] = [];

    if (r.library) {
      rows.push(
        { label: t('admin.backup.summary.artistsFollowed'), value: r.library.artists_followed },
        { label: t('admin.backup.summary.artistsExisting'), value: r.library.artists_existing },
        { label: t('admin.backup.summary.albumsQueued'), value: r.library.albums_queued },
        { label: t('admin.backup.summary.albumsCovered'), value: r.library.albums_covered_by_artist },
        { label: t('admin.backup.summary.albumsExisting'), value: r.library.albums_existing },
        { label: t('admin.backup.summary.chartsCreated'), value: r.library.charts_created },
        { label: t('admin.backup.summary.chartsExisting'), value: r.library.charts_existing },
      );
      if (r.library.charts_skipped) {
        rows.push({ label: t('admin.backup.summary.chartsSkipped'), value: r.library.charts_skipped });
      }
    }
    if (r.catalog) {
      rows.push(
        { label: t('admin.backup.summary.catalogRows'), value: `${r.catalog.artists} / ${r.catalog.albums} / ${r.catalog.tracks}` },
        { label: t('admin.backup.summary.tracksOnDisk'), value: r.catalog.tracks_on_disk },
        { label: t('admin.backup.summary.tracksToDownload'), value: r.catalog.tracks_to_download },
        { label: t('admin.backup.summary.albumsToImport'), value: r.catalog.albums_to_import },
      );
    }
    if (r.users) {
      rows.push(
        { label: t('admin.backup.summary.usersCreated'), value: r.users.created },
        { label: t('admin.backup.summary.usersSkipped'), value: r.users.skipped.length ? r.users.skipped.join(', ') : 0 },
      );
    }
    if (r.settings) {
      rows.push(
        { label: t('admin.backup.summary.settingsApplied'), value: r.settings.applied },
        { label: t('admin.backup.summary.settingsIgnored'), value: r.settings.ignored.length ? r.settings.ignored.join(', ') : 0 },
      );
    }

    return (
      <div className="space-y-4">
        <div className="divide-y divide-slate-200 dark:divide-white/10">
          {rows.map(row => (
            <div key={row.label} className="flex items-start justify-between gap-4 py-2 text-sm">
              <span className="text-muted-foreground">{row.label}</span>
              <span className="font-semibold text-foreground text-right break-all">{row.value}</span>
            </div>
          ))}
        </div>

        {r.warnings.length > 0 && (
          <div className="bg-amber-500/10 rounded-xl p-4 border border-amber-500/20 space-y-1">
            {r.warnings.map((w, i) => (
              <p key={i} className="text-sm text-amber-700 dark:text-amber-400">
                ⚠️ {t(`admin.backup.warnings.${w.code}`)}
                {w.detail && (
                  <span className="text-muted-foreground"> — {w.detail}</span>
                )}
              </p>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-8">
      {/* Export */}
      <section>
        <SectionHeader>{t('admin.backup.export.title')}</SectionHeader>
        <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10 space-y-4">
          <p className="text-sm text-muted-foreground">{t('admin.backup.export.description')}</p>

          {(['library', 'charts', 'catalog', 'users', 'settings'] as const).map(key => (
            <div key={key} className="flex items-center justify-between py-3 border-b border-slate-200 dark:border-white/10 last:border-0">
              <div className="flex-1 mr-4">
                <label className="font-semibold text-foreground block mb-1">
                  {t(`admin.backup.export.options.${key}.label`)}
                </label>
                <p className="text-sm text-muted-foreground">
                  {t(`admin.backup.export.options.${key}.description`)}
                </p>
              </div>
              <ToggleSwitch
                checked={options[key]}
                onChange={(checked) => setOptions(prev => ({ ...prev, [key]: checked }))}
              />
            </div>
          ))}

          {options.users && (
            <p className="text-sm text-amber-700 dark:text-amber-400">
              ⚠️ {t('admin.backup.export.usersWarning')}
            </p>
          )}

          <div className="flex justify-end">
            <Button
              onClick={handleExport}
              isLoading={exporting}
              disabled={!Object.values(options).some(Boolean)}
              variant="primary"
            >
              📤 {t('admin.backup.export.button')}
            </Button>
          </div>
        </div>
      </section>

      {/* Import */}
      <section>
        <SectionHeader>{t('admin.backup.import.title')}</SectionHeader>
        <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10 space-y-4">
          <p className="text-sm text-muted-foreground">{t('admin.backup.import.description')}</p>

          <div className="flex flex-col md:flex-row md:items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json,.json"
              onChange={handleFile}
              className="hidden"
              id="backup-import-file"
            />
            <Button
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={previewLoading || applying}
            >
              📥 {t('admin.backup.import.choose')}
            </Button>
            {fileName && (
              <span className="text-sm text-muted-foreground truncate">
                {fileName}
                {doc && ` — ${sectionsOf(doc).join(', ')}`}
              </span>
            )}
            {previewLoading && (
              <span className="text-sm text-muted-foreground">{t('admin.backup.import.previewing')}</span>
            )}
          </div>

          {importError && (
            <div className="bg-red-500/10 rounded-xl p-4 border border-red-500/20">
              <p className="text-sm text-red-600 dark:text-red-400 font-medium">{importError}</p>
            </div>
          )}

          {summary && (
            <div className="space-y-4">
              <h4 className="font-semibold text-foreground">
                {result ? t('admin.backup.import.resultTitle') : t('admin.backup.import.previewTitle')}
              </h4>
              {renderSummary(summary)}

              <div className="flex justify-end gap-3">
                <Button variant="ghost" onClick={resetImport} disabled={applying}>
                  {result ? t('common.close') : t('common.cancel')}
                </Button>
                {!result && (
                  <Button variant="primary" onClick={handleApply} isLoading={applying}>
                    {t('admin.backup.import.confirm')}
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};
