// src/components/ui/ConfirmDialog.tsx
import React, { useId } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Button } from './Button';
import { Modal } from './Modal';
import { Icon } from './icons';
import type { IconName } from './icons';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  /** Defaults to "Confirm" */
  confirmText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: 'danger' | 'warning' | 'info';
  isLoading?: boolean;
}

const ICONS: Record<'danger' | 'warning' | 'info', IconName> = {
  danger: 'trash',
  warning: 'warning',
  info: 'info',
};

const COLORS = {
  danger: 'bg-red-500/20 text-red-600 dark:text-red-400',
  warning: 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400',
  info: 'bg-accent-500/20 text-accent-600 dark:text-accent-400',
};

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  title,
  message,
  confirmText,
  onConfirm,
  onCancel,
  variant = 'danger',
  isLoading = false,
}) => {
  const { t } = useI18n();
  const titleId = useId();
  if (!isOpen) return null;

  return (
    <Modal onClose={onCancel} dismissible={!isLoading} labelledBy={titleId}>
      <div className="flex items-start gap-4 mb-6">
        <div className={`w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 ${COLORS[variant]}`}>
          <Icon name={ICONS[variant]} className="w-6 h-6" />
        </div>
        <div className="flex-1 min-w-0">
          <h2 id={titleId} className="text-xl font-bold text-foreground mb-2">
            {title}
          </h2>
          <p className="text-muted-foreground whitespace-pre-line">
            {message}
          </p>
        </div>
      </div>

      <div className="flex gap-3">
        <Button onClick={onCancel} variant="ghost" className="flex-1" disabled={isLoading}>
          {t('common.cancel')}
        </Button>
        <Button
          onClick={onConfirm}
          variant={variant === 'danger' ? 'danger' : 'primary'}
          className="flex-1"
          isLoading={isLoading}
        >
          {confirmText ?? t('common.confirm')}
        </Button>
      </div>
    </Modal>
  );
};
