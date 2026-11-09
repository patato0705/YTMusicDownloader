// src/components/QuickFollowButton.tsx
/**
 * Follow an artist straight from its card (Browse results, recommendations),
 * without opening its page. Same as the page's button: following downloads
 * everything and likes the artist; unfollowing asks first.
 *
 * Only for members and admins: the caller leaves it out for visitors.
 */
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../contexts/I18nContext';
import { useJobActivity } from '../contexts/JobActivityContext';
import { followArtist, unfollowArtist } from '../api/artists';
import { apiErrorMessage } from '../utils';
import { ConfirmDialog } from './ui/ConfirmDialog';
import { Spinner } from './ui/Spinner';
import { Toast } from './ui/Toast';
import { Icon } from './ui/icons';

interface QuickFollowButtonProps {
  artistId: string;
  name: string;
  followed: boolean;
  /** Told once the server has taken the change */
  onChange: (followed: boolean) => void;
}

export const QuickFollowButton: React.FC<QuickFollowButtonProps> = ({ artistId, name, followed, onChange }) => {
  const { t } = useI18n();
  const { refresh: refreshJobs } = useJobActivity();
  const [loading, setLoading] = useState(false);
  const [unfollowConfirm, setUnfollowConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (follow: boolean) => {
    setLoading(true);
    try {
      await (follow ? followArtist(artistId, name) : unfollowArtist(artistId));
      onChange(follow);
      refreshJobs();
    } catch (err) {
      console.error(follow ? 'Follow failed:' : 'Unfollow failed:', err);
      setError(apiErrorMessage(err, t, t('common.error')));
    } finally {
      setLoading(false);
      setUnfollowConfirm(false);
    }
  };

  const label = `${followed ? t('artist.unfollow') : t('artist.follow')}: ${name}`;

  return (
    <>
      <button
        type="button"
        onClick={() => (followed ? setUnfollowConfirm(true) : run(true))}
        disabled={loading}
        aria-label={label}
        aria-pressed={followed}
        title={followed ? t('artist.followed') : t('artist.follow')}
        className={`flex w-9 h-9 items-center justify-center rounded-full shadow-md ring-2 ring-white dark:ring-zinc-900 transition-all outline-none focus-visible:ring-accent-500/70 disabled:cursor-wait ${
          followed
            ? 'bg-accent-600 text-white hover:bg-accent-700'
            // Shown on hover where there is one, like the dismiss button
            : 'bg-white text-slate-700 hover:bg-accent-600 hover:text-white dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-accent-600 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 focus-visible:opacity-100'
        } ${loading ? '!opacity-100' : ''}`}
      >
        {loading ? (
          <Spinner size="sm" />
        ) : (
          <Icon name={followed ? 'check' : 'plus'} strokeWidth={2.5} className="w-4 h-4" />
        )}
      </button>

      <ConfirmDialog
        isOpen={unfollowConfirm}
        title={t('artist.unfollowTitle')}
        message={t('artist.unfollowMessage')}
        confirmText={t('artist.unfollow')}
        onConfirm={() => run(false)}
        onCancel={() => setUnfollowConfirm(false)}
        variant="warning"
        isLoading={loading}
      />

      {/* Out of the card: its hover lift (a transform) would pin a fixed toast to it */}
      {error && createPortal(<Toast message={error} type="error" onClose={() => setError(null)} />, document.body)}
    </>
  );
};
