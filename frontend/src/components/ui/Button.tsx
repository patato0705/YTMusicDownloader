// src/components/ui/Button.tsx
import React from 'react';
import { Spinner } from './Spinner';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  disabled,
  className = '',
  ...props
}) => {
  const baseStyles = 'inline-flex items-center justify-center font-semibold rounded-xl transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';
  
  const variants = {
    primary: 'bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-red-700 dark:to-red-600 text-white hover:shadow-lg hover:shadow-blue-500/50 dark:hover:shadow-red-700/50 focus:ring-blue-500 dark:focus:ring-red-600',
    secondary: 'bg-slate-200 dark:bg-zinc-800 text-slate-900 dark:text-zinc-100 hover:bg-slate-300 dark:hover:bg-zinc-700 focus:ring-slate-400 dark:focus:ring-zinc-600',
    outline: 'border-2 border-blue-500 dark:border-red-600 text-blue-600 dark:text-red-400 hover:bg-blue-50 dark:hover:bg-red-950/30 focus:ring-blue-500 dark:focus:ring-red-600',
    ghost: 'text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 focus:ring-slate-400 dark:focus:ring-zinc-600',
    danger: 'bg-red-600 dark:bg-red-700 text-white hover:bg-red-700 dark:hover:bg-red-800 hover:shadow-lg hover:shadow-red-500/50 focus:ring-red-500',
  };
  
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2.5 text-base',
    lg: 'px-6 py-3 text-lg',
  };

  return (
    <button
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading && <Spinner size="sm" className="-ml-1 mr-2" />}
      {children}
    </button>
  );
};