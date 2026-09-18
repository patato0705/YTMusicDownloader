// src/components/admin/SettingsTab.tsx
/**
 * Admin panel > Settings: edit application settings grouped by category,
 * plus the library cleanup maintenance action.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../ui/Button';
import { SectionHeader } from '../ui/SectionHeader';
import { Select } from '../ui/Select';
import { ToggleSwitch } from '../ui/ToggleSwitch';
import * as adminApi from '../../api/admin';
import type { Setting, YoutubeCookiesStatus } from '../../api/admin';
import { cleanupLibrary } from '../../api/library';
import type { CleanupResult } from '../../api/library';
import { parseApiError } from '../../utils';
import { AdminTabShell } from './AdminTabShell';
import type { AdminTabProps } from './AdminTabShell';

interface SettingsTabProps extends AdminTabProps {
  /** Called after a successful save; feature flags may have changed. */
  onSaved?: () => void;
}

export const SettingsTab: React.FC<SettingsTabProps> = ({ onToast, onSaved }) => {
  const { t, locale } = useI18n();

  const [settings, setSettings] = useState<Setting[]>([]);
  const [editedSettings, setEditedSettings] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [cleanupLoading, setCleanupLoading] = useState(false);

  // YouTube account cookies (fallback jar for age-restricted tracks)
  const [cookies, setCookies] = useState<YoutubeCookiesStatus | null>(null);
  const [cookiesBusy, setCookiesBusy] = useState(false);
  const cookiesFileRef = useRef<HTMLInputElement>(null);

  // t() hands back the key itself when a translation is missing; settings are
  // defined on the backend, so fall back to the backend's English text.
  const tr = (key: string, fallback: string): string => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  // Localized language names for the ytmusic.language dropdown
  const languageNames = useMemo(() => {
    try {
      return new Intl.DisplayNames([locale], { type: 'language' });
    } catch {
      return null;
    }
  }, [locale]);

  const loadSettings = async () => {
    const [settingsArray, cookiesStatus] = await Promise.all([
      adminApi.getAllSettings(),
      adminApi.getYoutubeCookies(),
    ]);
    setSettings(settingsArray);
    setCookies(cookiesStatus);

    // Initialize edited settings
    const initial: Record<string, any> = {};
    settingsArray.forEach(setting => {
      initial[setting.key] = setting.value;
    });
    setEditedSettings(initial);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        await loadSettings();
      } catch (err: any) {
        console.error('Failed to load settings:', err);
        if (!cancelled) setError(parseApiError(err, 'Failed to load data'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleSettingChange = (key: string, value: any, type: string) => {
    let parsedValue = value;

    if (type === 'int') {
      // Keep an emptied field empty (rather than NaN) so it can be typed into;
      // saveSettings() refuses to submit it.
      parsedValue = value === '' ? '' : Number(value);
    } else if (type === 'bool') {
      parsedValue = value === 'true' || value === true;
    }

    setEditedSettings(prev => ({
      ...prev,
      [key]: parsedValue,
    }));
  };

  const settingLabel = (setting: Setting): string =>
    tr(
      `admin.settings.keys.${setting.key}.label`,
      setting.key.split('.').slice(1).join('.').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
    );

  const settingDescription = (setting: Setting): string =>
    tr(`admin.settings.keys.${setting.key}.description`, setting.description ?? '');

  const settingOptionLabel = (setting: Setting, option: adminApi.SettingOption): string => {
    const translated = t(`admin.settings.options.${setting.key}.${option.value}`);
    if (translated !== `admin.settings.options.${setting.key}.${option.value}`) return translated;
    if (setting.key === 'ytmusic.language' && languageNames) {
      try {
        const name = languageNames.of(option.value.replace('_', '-'));
        if (name) return name.charAt(0).toUpperCase() + name.slice(1);
      } catch {
        // unknown tag — use the backend label
      }
    }
    return option.label;
  };

  const invalidIntSetting = (setting: Setting): boolean => {
    if (setting.type !== 'int') return false;
    const value = editedSettings[setting.key];
    return (
      !Number.isInteger(value) ||
      (setting.min != null && value < setting.min) ||
      (setting.max != null && value > setting.max)
    );
  };

  const saveSettings = async () => {
    const invalid = settings.find(invalidIntSetting);
    if (invalid) {
      const params = { name: settingLabel(invalid), min: invalid.min ?? 0, max: invalid.max ?? 0 };
      onToast(
        t(invalid.max != null ? 'admin.settings.invalidNumberRange' : 'admin.settings.invalidNumber', params),
        'error',
      );
      return;
    }

    setSaveLoading(true);
    setError(null);

    try {
      // Update each changed setting
      const updatePromises = Object.entries(editedSettings).map(([key, value]) => {
        const originalSetting = settings.find(s => s.key === key);
        if (originalSetting && originalSetting.value !== value) {
          return adminApi.updateSetting(key, value);
        }
        return Promise.resolve();
      });

      await Promise.all(updatePromises);

      await loadSettings();
      onSaved?.();
      onToast(t('admin.settings.saved'), 'success');
    } catch (err: any) {
      onToast(parseApiError(err, t('admin.settings.saveFailed')), 'error');
    } finally {
      setSaveLoading(false);
    }
  };

  const handleCleanup = async () => {
    setCleanupLoading(true);
    try {
      const result: CleanupResult = await cleanupLibrary();
      const total = result.orphaned_tracks_removed + result.orphaned_albums_removed + result.orphaned_artists_removed;
      if (total === 0) {
        onToast(t('admin.settings.cleanupNone'), 'success');
      } else {
        const parts: string[] = [];
        if (result.orphaned_artists_removed > 0) parts.push(`${result.orphaned_artists_removed} artists`);
        if (result.orphaned_albums_removed > 0) parts.push(`${result.orphaned_albums_removed} albums`);
        if (result.orphaned_tracks_removed > 0) parts.push(`${result.orphaned_tracks_removed} tracks`);
        onToast(`${t('admin.settings.cleanupDone')}: ${parts.join(', ')} removed`, 'success');
      }
    } catch (err: any) {
      onToast(parseApiError(err), 'error');
    } finally {
      setCleanupLoading(false);
    }
  };

  const handleCookiesFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setCookiesBusy(true);
    try {
      const content = await file.text();
      setCookies(await adminApi.uploadYoutubeCookies(content));
      onToast(t('admin.settings.cookies.uploaded'), 'success');
    } catch (err: any) {
      onToast(parseApiError(err, t('admin.settings.cookies.uploadFailed')), 'error');
    } finally {
      setCookiesBusy(false);
    }
  };

  const handleCookiesDelete = async () => {
    setCookiesBusy(true);
    try {
      await adminApi.deleteYoutubeCookies();
      setCookies({ present: false, cookie_count: 0, size_bytes: 0, modified_at: null });
      onToast(t('admin.settings.cookies.deleted'), 'success');
    } catch (err: any) {
      onToast(parseApiError(err), 'error');
    } finally {
      setCookiesBusy(false);
    }
  };

  const cookiesStatusText = (): string => {
    if (!cookies?.present) return t('admin.settings.cookies.none');
    const when = cookies.modified_at ? new Date(cookies.modified_at).toLocaleString(locale) : '';
    return t('admin.settings.cookies.present', { count: cookies.cookie_count, date: when });
  };

  // Group settings by category
  const grouped: Record<string, Setting[]> = {};
  settings.forEach(setting => {
    const category = setting.key.split('.')[0];
    if (!grouped[category]) grouped[category] = [];
    grouped[category].push(setting);
  });

  return (
    <AdminTabShell loading={loading} error={error}>
      <div className="space-y-8">
        {Object.entries(grouped).map(([category, categorySettings]) => (
          <section key={category}>
            <SectionHeader>
              {tr(`admin.settings.categories.${category}`, category.charAt(0).toUpperCase() + category.slice(1))}
            </SectionHeader>

            <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10 space-y-4">
              {categorySettings.map(setting => (
                <div key={setting.key} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 py-3 border-b border-slate-200 dark:border-white/10 last:border-0">
                  <div className="flex-1 basis-40 min-w-0">
                    <label className="font-semibold text-foreground block mb-1">
                      {settingLabel(setting)}
                    </label>
                    <p className="text-sm text-muted-foreground">{settingDescription(setting)}</p>
                  </div>

                  <div className="flex-shrink-0 ml-auto">
                    {setting.type === 'bool' ? (
                      <ToggleSwitch
                        checked={!!editedSettings[setting.key]}
                        onChange={(checked) => handleSettingChange(setting.key, checked, setting.type)}
                      />
                    ) : setting.type === 'int' ? (
                      <input
                        type="number"
                        min={setting.min ?? undefined}
                        max={setting.max ?? undefined}
                        step={1}
                        value={editedSettings[setting.key] ?? ''}
                        onChange={(e) => handleSettingChange(setting.key, e.target.value, setting.type)}
                        className={`w-24 px-3 py-2 glass rounded-xl text-foreground text-center focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 ${
                          invalidIntSetting(setting)
                            ? 'border border-red-500 dark:border-red-500'
                            : 'border-slate-200 dark:border-white/10'
                        }`}
                      />
                    ) : Array.isArray(setting.allowed_values) && setting.allowed_values.length > 0 ? (
                      <Select
                        value={editedSettings[setting.key] ?? ''}
                        onChange={(value) => handleSettingChange(setting.key, value, setting.type)}
                        options={setting.allowed_values.map(option => ({
                          value: option.value,
                          label: settingOptionLabel(setting, option),
                        }))}
                        className="w-48"
                      />
                    ) : (
                      <input
                        type="text"
                        value={editedSettings[setting.key] ?? ''}
                        onChange={(e) => handleSettingChange(setting.key, e.target.value, setting.type)}
                        className="w-48 px-3 py-2 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600"
                      />
                    )}
                  </div>
                </div>
              ))}

              {category === 'download' && (
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 py-3">
                  <div className="flex-1 basis-40 min-w-0">
                    <label className="font-semibold text-foreground block mb-1">
                      {t('admin.settings.cookies.label')}
                    </label>
                    <p className="text-sm text-muted-foreground">{t('admin.settings.cookies.description')}</p>
                    <p className={`text-sm mt-1 ${cookies?.present ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
                      {cookiesStatusText()}
                    </p>
                  </div>
                  <div className="flex-shrink-0 ml-auto flex items-center gap-2">
                    <input
                      ref={cookiesFileRef}
                      type="file"
                      accept="text/plain,.txt"
                      onChange={handleCookiesFile}
                      className="hidden"
                      id="youtube-cookies-file"
                    />
                    <Button
                      variant="outline"
                      onClick={() => cookiesFileRef.current?.click()}
                      disabled={cookiesBusy}
                    >
                      {cookies?.present ? t('admin.settings.cookies.replace') : t('admin.settings.cookies.upload')}
                    </Button>
                    {cookies?.present && (
                      <Button variant="outline" onClick={handleCookiesDelete} disabled={cookiesBusy}>
                        {t('admin.settings.cookies.remove')}
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </section>
        ))}

        <div className="flex justify-end">
          <Button
            onClick={saveSettings}
            isLoading={saveLoading}
            variant="primary"
            size="lg"
          >
            {t('admin.settings.save')}
          </Button>
        </div>

        {/* Maintenance */}
        <section>
          <SectionHeader>{t('admin.settings.maintenance')}</SectionHeader>

          <div className="glass rounded-2xl p-6 border border-slate-200/50 dark:border-white/10 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 py-3">
              <div className="flex-1 basis-40 min-w-0">
                <label className="font-semibold text-foreground block mb-1">
                  {t('admin.settings.cleanupTitle')}
                </label>
                <p className="text-sm text-muted-foreground">
                  {t('admin.settings.cleanupDescription')}
                </p>
              </div>
              <div className="flex-shrink-0 ml-auto">
                <Button
                  onClick={handleCleanup}
                  isLoading={cleanupLoading}
                  variant="outline"
                >
                  {t('admin.settings.cleanupButton')}
                </Button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </AdminTabShell>
  );
};
