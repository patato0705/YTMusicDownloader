// src/components/ui/LikeButton.tsx
/**
 * Heart toggling whether you like an artist of the library: your
 * recommendations come from the artists you like
 * (backend/services/recommendations.py). Looks are up to the caller.
 */
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';

export const HeartIcon: React.FC<{ filled: boolean; className?: string }> = ({ filled, className = '' }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill={filled ? 'currentColor' : 'none'}
    stroke="currentColor"
    strokeWidth={2}
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M12 20.25s-7.5-4.6-7.5-10.1A4.15 4.15 0 0112 7.6a4.15 4.15 0 017.5 2.55c0 5.5-7.5 10.1-7.5 10.1z"
    />
  </svg>
);

interface LikeButtonProps {
  liked: boolean;
  /** The artist's name, for screen readers */
  name: string;
  onToggle: () => void;
  className?: string;
  iconClassName?: string;
}

export const LikeButton: React.FC<LikeButtonProps> = ({ liked, name, onToggle, className = '', iconClassName = 'w-4 h-4' }) => {
  const { t } = useI18n();
  const label = t(liked ? 'artist.unlike' : 'artist.like');
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={liked}
      aria-label={`${label}: ${name}`}
      title={label}
      className={`flex items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70 dark:focus-visible:ring-red-500/70 ${className}`}
    >
      <HeartIcon filled={liked} className={`${iconClassName} ${liked ? 'text-rose-500' : ''}`} />
    </button>
  );
};
