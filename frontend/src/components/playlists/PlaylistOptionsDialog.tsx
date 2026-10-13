// src/components/playlists/PlaylistOptionsDialog.tsx
/**
 * Add a playlist to the library, or change how it's added
 * (backend/services/playlists.py): what its songs bring in (their albums or
 * their main artists), whether it's followed (rescanned on a schedule) and
 * whether it's written as an M3U file. Editing also offers removing it.
 */
import React, { useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from '../ui/Button';
import { ToggleSwitch } from '../ui/ToggleSwitch';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { Modal } from '../ui/Modal';
import { ErrorBanner } from '../ui/PageStatus';
import { addPlaylist, updatePlaylist, removePlaylist } from '../../api/playlists';
import type { PlaylistMode, SavedPlaylist } from '../../api/playlists';
import { apiErrorMessage } from '../../utils';

interface PlaylistOptionsDialogProps {
  playlistId: string;
  playlistTitle: string;
  /** The playlist as added, when editing */
  saved?: SavedPlaylist | null;
  onClose: () => void;
  onSaved: (saved: SavedPlaylist) => void;
  onRemoved?: () => void;
}

export const PlaylistOptionsDialog: React.FC<PlaylistOptionsDialogProps> = ({
  playlistId,
  playlistTitle,
  saved,
  onClose,
  onSaved,
  onRemoved,
}) => {
  const { t } = useI18n();
  const editing = !!saved;
  const [mode, setMode] = useState<PlaylistMode>(saved?.mode ?? 'albums');
  const [followed, setFollowed] = useState(saved?.followed ?? true);
  const [m3u, setM3u] = useState(saved?.m3u ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  const valid = followed || m3u;
  const unchanged = editing && saved!.mode === mode && saved!.followed === followed && saved!.m3u === m3u;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = editing
        ? await updatePlaylist(playlistId, { mode, followed, m3u })
        : await addPlaylist(playlistId, { mode, followed, m3u });
      onSaved(result);
      onClose();
    } catch (err: any) {
      setError(apiErrorMessage(err, t, t('common.error')));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await removePlaylist(playlistId);
      setConfirmRemove(false);
      onRemoved?.();
      onClose();
    } catch (err: any) {
      setConfirmRemove(false);
      setError(apiErrorMessage(err, t, t('common.error')));
    } finally {
      setBusy(false);
    }
  };

  // What a change does to a playlist already added
  const modeNote = editing && saved!.mode !== mode
    ? t(mode === 'artists' ? 'playlist.options.switchToArtists' : 'playlist.options.switchToAlbums')
    : null;

  return (
    <Modal
      title={t(editing ? 'playlist.options.editTitle' : 'playlist.options.addTitle')}
      subtitle={playlistTitle}
      onClose={onClose}
      dismissible={!busy}
      size="lg"
    >
      {error && <ErrorBanner className="mb-5">{error}</ErrorBanner>}

      {/* What its songs bring in */}
      <fieldset className="mb-6">
        <legend className="text-sm font-semibold text-foreground mb-3">{t('playlist.options.bringIn')}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          {(['albums', 'artists'] as const).map((value) => {
            const selected = mode === value;
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setMode(value)}
                className={`text-left rounded-2xl p-4 border transition-colors ${
                  selected
                    ? 'border-blue-500 bg-blue-500/10 dark:border-red-500 dark:bg-red-500/10'
                    : 'border-slate-200 dark:border-white/10 hover:bg-slate-100/60 dark:hover:bg-white/5'
                }`}
              >
                <span className={`block font-semibold mb-1 ${selected ? 'text-blue-700 dark:text-red-400' : 'text-foreground'}`}>
                  {t(`playlist.options.${value}`)}
                </span>
                <span className="block text-xs text-muted-foreground">{t(`playlist.options.${value}Description`)}</span>
              </button>
            );
          })}
        </div>
        {modeNote && <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">{modeNote}</p>}
      </fieldset>

      {/* Followed / once, M3U */}
      <div className="space-y-4 mb-6">
        <OptionRow
          label={t('playlist.options.follow')}
          description={t(followed ? 'playlist.options.followOn' : 'playlist.options.followOff')}
          checked={followed}
          onChange={setFollowed}
        />
        <OptionRow
          label={t('playlist.options.m3u')}
          description={t('playlist.options.m3uDescription')}
          checked={m3u}
          onChange={setM3u}
        />
        {!valid && (
          <p className="text-xs text-red-600 dark:text-red-400">{t('playlist.options.needOne')}</p>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        {editing ? (
          <Button variant="ghost" size="sm" onClick={() => setConfirmRemove(true)} disabled={busy}
            className="!text-red-600 dark:!text-red-400">
            {t('playlist.options.remove')}
          </Button>
        ) : <span />}
        <div className="flex gap-3 ml-auto">
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
          <Button variant="primary" onClick={submit} isLoading={busy} disabled={!valid || unchanged}>
            {t(editing ? 'common.save' : 'playlist.options.add')}
          </Button>
        </div>
      </div>

      <ConfirmDialog
        isOpen={confirmRemove}
        title={t('playlist.options.removeTitle')}
        message={t('playlist.options.removeMessage')}
        confirmText={t('playlist.options.remove')}
        onConfirm={remove}
        onCancel={() => setConfirmRemove(false)}
        isLoading={busy}
      />
    </Modal>
  );
};

const OptionRow: React.FC<{
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}> = ({ label, description, checked, onChange }) => (
  <div className="flex items-start justify-between gap-4">
    <div className="min-w-0">
      <p className="text-sm font-semibold text-foreground">{label}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
    </div>
    <ToggleSwitch checked={checked} onChange={onChange} ariaLabel={label} className="flex-shrink-0 mt-0.5" />
  </div>
);

