// src/components/ui/Button.tsx
import React from 'react';
import { Spinner } from './Spinner';

const BASE = 'inline-flex items-center justify-center font-semibold rounded-xl transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

/** danger: the final confirm of a destructive action; subtleDanger: the button that opens that confirm */
const VARIANTS = {
  primary: 'bg-accent-600 text-white hover:bg-accent-700 dark:bg-accent-500 dark:hover:bg-accent-600 focus:ring-accent-500',
  secondary: 'bg-slate-200 dark:bg-zinc-800 text-slate-900 dark:text-zinc-100 hover:bg-slate-300 dark:hover:bg-zinc-700 focus:ring-slate-400 dark:focus:ring-zinc-600',
  outline: 'border-2 border-accent-500 dark:border-accent-600 text-accent-600 dark:text-accent-400 hover:bg-accent-50 dark:hover:bg-accent-950/30 focus:ring-accent-500 dark:focus:ring-accent-600',
  ghost: 'text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 focus:ring-slate-400 dark:focus:ring-zinc-600',
  danger: 'bg-red-600 dark:bg-red-700 text-white hover:bg-red-700 dark:hover:bg-red-800 focus:ring-red-500',
  subtleDanger: 'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 focus:ring-red-500',
};

const SIZES = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2.5 text-base',
  lg: 'px-6 py-3 text-lg',
};

export type ButtonVariant = keyof typeof VARIANTS;
export type ButtonSize = keyof typeof SIZES;

/** A button's look, for things that act like one but aren't a <button> (e.g. a Link) */
export const buttonClass = (variant: ButtonVariant = 'primary', size: ButtonSize = 'md'): string =>
  `${BASE} ${VARIANTS[variant]} ${SIZES[size]}`;

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
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
  return (
    <button
      className={`${buttonClass(variant, size)} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading && <Spinner size="sm" className="-ml-1 mr-2" />}
      {children}
    </button>
  );
};