// src/components/ui/Toast.tsx
import React, { useEffect } from 'react';

export interface ToastProps {
  message: string;
  type?: 'success' | 'error' | 'info';
  duration?: number;
  onClose: () => void;
}

export const Toast: React.FC<ToastProps> = ({ 
  message, 
  type = 'success', 
  duration = 3000,
  onClose 
}) => {
  useEffect(() => {
    const timer = setTimeout(onClose, duration);
    return () => clearTimeout(timer);
  }, [duration, onClose]);

  const icons = {
    success: '✓',
    error: '✗',
    info: 'ℹ'
  };

  const colors = {
    success: 'bg-green-500/10 dark:bg-green-500/5 border-green-500/50 text-green-600 dark:text-green-400',
    error: 'bg-red-500/10 dark:bg-red-500/5 border-red-500/50 text-red-600 dark:text-red-400',
    info: 'bg-blue-500/10 dark:bg-blue-500/5 border-blue-500/50 text-blue-600 dark:text-blue-400'
  };

  return (
    <div className="fixed top-24 right-4 z-[100] animate-in slide-in-from-top-2 fade-in duration-300">
      <div className={`glass rounded-2xl p-4 border shadow-2xl ${colors[type]} min-w-[300px] max-w-md`}>
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-lg ${
            type === 'success' ? 'bg-green-500/20' : 
            type === 'error' ? 'bg-red-500/20' : 
            'bg-blue-500/20'
          }`}>
            {icons[type]}
          </div>
          <p className="flex-1 font-medium">{message}</p>
          <button
            onClick={onClose}
            className="text-current hover:opacity-70 transition-opacity"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
};