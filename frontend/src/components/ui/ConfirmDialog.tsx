// src/components/ui/ConfirmDialog.tsx
import React from 'react';
import { Button } from './Button';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: 'danger' | 'warning' | 'info';
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  onConfirm,
  onCancel,
  variant = 'danger',
}) => {
  if (!isOpen) return null;

  const icons = {
    danger: '🗑️',
    warning: '⚠️',
    info: 'ℹ️',
  };

  const colors = {
    danger: 'bg-red-500/20 text-red-600 dark:text-red-400',
    warning: 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400',
    info: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 animate-in fade-in duration-200">
      <div className="glass rounded-3xl p-8 max-w-md w-full border-gradient shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-start gap-4 mb-6">
          <div className={`w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 ${colors[variant]}`}>
            <span className="text-2xl">{icons[variant]}</span>
          </div>
          <div className="flex-1">
            <h2 className="text-xl font-bold text-foreground mb-2">
              {title}
            </h2>
            <p className="text-muted-foreground">
              {message}
            </p>
          </div>
        </div>

        <div className="flex gap-3">
          <Button
            onClick={onCancel}
            variant="ghost"
            className="flex-1"
          >
            {cancelText}
          </Button>
          <Button
            onClick={onConfirm}
            variant={variant === 'danger' ? 'danger' : 'primary'}
            className="flex-1"
          >
            {confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
};