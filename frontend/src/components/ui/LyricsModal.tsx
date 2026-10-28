// src/components/ui/LyricsModal.tsx
import React, { useEffect, useState } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from './Button';
import { Spinner } from './Spinner';
import { LyricsBadge } from './LyricsBadge';
import { Modal } from './Modal';
import { ErrorBanner } from './PageStatus';
import { getTrackLyrics, updateTrackLyrics } from '../../api/tracks';
import { apiErrorMessage, primaryArtistName } from '../../utils';
import type { LyricsKind, Track } from '../../types';
import { Icon } from './icons';

// Same rule as backend/routers/tracks.py's _LRC_TIMESTAMP_RE: a line that
// starts with [mm:ss.xx] makes the whole file "synced".
const LRC_TIMESTAMP_RE = /^\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]/m;

function classifyLyrics(content: string): LyricsKind {
  if (!content.trim()) return null;
  return LRC_TIMESTAMP_RE.test(content) ? 'synced' : 'plain';
}

/** LRCLIB's site search; artist + title only, since album name is what
 *  usually makes the automatic lookup miss. */
function lrclibSearchUrl(track: Track): string {
  const query = `${primaryArtistName(track)} ${track.title}`.trim();
  return `https://lrclib.net/search/${encodeURIComponent(query)}`;
}

interface LyricsModalProps {
  track: Track;
  /** Whether the current user may write lyrics (member/admin) */
  canEdit: boolean;
  onClose: () => void;
  /** Called with the updated track after a successful save */
  onSaved: (track: Track) => void;
}

export const LyricsModal: React.FC<LyricsModalProps> = ({ track, canEdit, onClose, onSaved }) => {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [original, setOriginal] = useState('');
  const [draft, setDraft] = useState('');
  // False when the audio isn't on disk yet: there's nowhere to write the .lrc.
  const [editable, setEditable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');

    getTrackLyrics(track.id)
      .then((data) => {
        if (cancelled) return;
        const content = data.content ?? '';
        setOriginal(content);
        setDraft(content);
        setEditable(data.editable);
      })
      .catch((err) => {
        if (!cancelled) setError(apiErrorMessage(err, t, t('common.error')));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [track.id]);

  const dirty = draft !== original;
  const isEditing = canEdit && editable;
  const draftKind = classifyLyrics(draft);
  const clearing = dirty && draftKind === null;

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      const result = await updateTrackLyrics(track.id, draft);
      onSaved({ ...track, ...result.track });
      onClose();
    } catch (err: any) {
      setError(apiErrorMessage(err, t, t('common.error')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={track.title}
      subtitle={primaryArtistName(track) || t('album.unknownArtist')}
      headerExtra={<LyricsBadge kind={track.lyrics} />}
      onClose={onClose}
      dismissible={!dirty && !saving}
      size="xl"
      className="flex flex-col"
    >
      {error && <ErrorBanner className="mb-4">{error}</ErrorBanner>}

      {/* LRCLIB link */}
      <a
        href={lrclibSearchUrl(track)}
        target="_blank"
        rel="noopener noreferrer"
        className="glass rounded-2xl p-4 border border-slate-200/50 dark:border-white/10 flex items-center gap-3 mb-4 shrink-0 hover:border-accent-500/40 transition-colors group"
      >
        <Icon name="search" className="w-6 h-6" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-foreground group-hover:text-accent-600 dark:group-hover:text-accent-400 transition-colors">
            {t('lyrics.searchLrclib')}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">{t('lyrics.searchLrclibHint')}</p>
        </div>
        <span className="text-muted-foreground text-sm">↗</span>
      </a>

      {/* Editor */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Spinner size="lg" className="text-accent-600 dark:text-accent-500" />
        </div>
      ) : (
        <div className="flex-1 flex flex-col">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            readOnly={!isEditing}
            spellCheck={false}
            placeholder={isEditing ? t('lyrics.placeholder') : t('lyrics.empty')}
            className="flex-1 min-h-[16rem] [@media(max-height:500px)]:min-h-[6rem] w-full resize-none rounded-2xl p-4 font-mono text-sm leading-relaxed bg-white/60 dark:bg-black/30 border border-slate-200/50 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-accent-500 dark:focus:ring-accent-600 read-only:opacity-80"
          />
          <div className="flex items-center justify-between gap-3 mt-2 px-1 min-h-[1.25rem]">
            <p className="text-xs text-muted-foreground">
              {!editable
                ? t('lyrics.notDownloaded')
                : !canEdit
                  ? t('lyrics.readOnly')
                  : dirty
                    ? draftKind
                      ? t('lyrics.willSaveAs', { kind: t(`lyrics.kind.${draftKind}`) })
                      : t('lyrics.willClear')
                    : t('lyrics.formatHint')}
            </p>
            {track.lyrics_local && (
              <p className="text-xs text-muted-foreground font-mono truncate max-w-[50%]" title={track.lyrics_local}>
                {track.lyrics_local.split('/').pop()}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3 pt-5 shrink-0">
        <Button type="button" variant="ghost" onClick={onClose} disabled={saving} className="flex-1">
          {isEditing ? t('common.cancel') : t('common.close')}
        </Button>
        {isEditing && (
          <Button
            type="button"
            variant={clearing ? 'danger' : 'primary'}
            onClick={handleSave}
            isLoading={saving}
            disabled={!dirty || loading}
            className="flex-1"
          >
            {clearing ? t('lyrics.clear') : t('common.save')}
          </Button>
        )}
      </div>
    </Modal>
  );
};
