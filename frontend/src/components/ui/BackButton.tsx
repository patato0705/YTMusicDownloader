// src/components/ui/BackButton.tsx
/**
 * Arrow going back to the previous page. Opened from a link with no
 * history in this app (a new tab, a bookmark), it goes to Browse instead.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../../contexts/I18nContext';
import { Icon } from './icons';

/** Size and placement come from the caller */
export const BackButton: React.FC<{ className?: string }> = ({ className = '' }) => {
  const navigate = useNavigate();
  const { t } = useI18n();
  // React Router numbers its history entries: 0 is where the app was entered
  const canGoBack = (window.history.state?.idx ?? 0) > 0;

  return (
    <button
      type="button"
      onClick={() => (canGoBack ? navigate(-1) : navigate('/browse'))}
      aria-label={t('common.back')}
      title={t('common.back')}
      className={`inline-flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-slate-200/70 dark:hover:bg-white/10 transition-colors ${className}`}
    >
      <Icon name="arrowLeft" className="w-4 h-4 md:w-5 md:h-5" />
    </button>
  );
};
