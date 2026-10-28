// src/components/ui/Toast.tsx
import React, { useEffect, useRef } from 'react';
import { useI18n } from '../../contexts/I18nContext';

export interface ToastProps {
  message: string;
  type?: 'success' | 'error' | 'info';
  duration?: number;
  /** A button next to the message, e.g. "Undo"; closes the toast once clicked */
  action?: { label: string; onClick: () => void };
  onClose: () => void;
}

export const Toast: React.FC<ToastProps> = ({ 
  message, 
  type = 'success', 
  duration = 3000,
  action,
  onClose 
}) => {
  const { t } = useI18n();
  // The timer starts once: a parent passing a new onClose on each render
  // (an inline arrow) mustn't push the dismissal back
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const timer = setTimeout(() => onCloseRef.current(), duration);
    return () => clearTimeout(timer);
  }, [duration, message]);

  const icons = {
    success: '✓',
    error: '✗',
    info: 'ℹ'
  };

  const colors = {
    success: 'bg-green-500/10 dark:bg-green-500/5 border-green-500/50 text-green-600 dark:text-green-400',
    error: 'bg-red-500/10 dark:bg-red-500/5 border-red-500/50 text-red-600 dark:text-red-400',
    info: 'bg-accent-500/10 dark:bg-accent-500/5 border-accent-500/50 text-accent-600 dark:text-accent-400'
  };

  return (
    <div role="status" className="fixed top-24 right-4 z-[100]">
      <div className={`glass rounded-2xl p-4 border shadow-2xl ${colors[type]} min-w-[300px] max-w-md`}>
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-lg ${
            type === 'success' ? 'bg-green-500/20' : 
            type === 'error' ? 'bg-red-500/20' : 
            'bg-accent-500/20'
          }`}>
            {icons[type]}
          </div>
          <p className="flex-1 font-medium">{message}</p>
          {action && (
            <button
              onClick={() => { action.onClick(); onClose(); }}
              className="px-3 py-1 rounded-lg text-sm font-semibold bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15 transition-colors"
            >
              {action.label}
            </button>
          )}
          <button
            onClick={onClose}
            aria-label={t('common.close')}
            className="text-current hover:opacity-70 transition-opacity"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
};