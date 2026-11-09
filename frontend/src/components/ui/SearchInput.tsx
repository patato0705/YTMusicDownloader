// src/components/ui/SearchInput.tsx
import React, { useRef } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Spinner } from './Spinner';
import { Icon } from './icons';

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  /** Defaults to "Search..." */
  placeholder?: string;
  onFocus?: () => void;
  autoFocus?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  /** Extra classes on the <input> itself (the wrapper gets `className`) */
  inputClassName?: string;
  loading?: boolean;
}

const sizeClasses = {
  sm: 'pl-10 py-2.5 text-sm',
  md: 'pl-12 py-3 text-base',
  lg: 'pl-16 py-4 text-lg',
};

/** Right padding by number of trailing controls (none, one, spinner + clear) */
const rightPadding = {
  sm: ['pr-4', 'pr-9', 'pr-16'],
  md: ['pr-4', 'pr-11', 'pr-[4.5rem]'],
  lg: ['pr-16', 'pr-16', 'pr-24'],
};

const iconSizes = {
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-6 h-6',
};

const iconPadding = {
  sm: 'pl-3',
  md: 'pl-4',
  lg: 'pl-5',
};

const trailingPadding = {
  sm: 'pr-2.5',
  md: 'pr-3',
  lg: 'pr-4',
};

export const SearchInput: React.FC<SearchInputProps> = ({
  value,
  onChange,
  placeholder,
  onFocus,
  autoFocus = false,
  size = 'md',
  className = '',
  inputClassName = '',
  loading = false,
}) => {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const label = placeholder ?? t('common.searchPlaceholder');
  const trailingCount = (loading ? 1 : 0) + (value ? 1 : 0);

  const clear = () => {
    onChange('');
    inputRef.current?.focus();
  };

  return (
    <div className={`relative ${className}`}>
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape' && value) {
            e.preventDefault();
            clear();
          }
        }}
        onFocus={onFocus}
        placeholder={label}
        autoFocus={autoFocus}
        className={`w-full ${sizeClasses[size]} ${rightPadding[size][trailingCount]} glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-accent-500 dark:focus:ring-accent-600 focus:border-transparent transition-all duration-300 ${size === 'lg' ? 'shadow-lg' : ''} ${inputClassName}`}
        aria-label={label}
      />

      {/* Search icon */}
      <div className={`absolute inset-y-0 left-0 ${iconPadding[size]} flex items-center pointer-events-none z-10`}>
        <Icon name="search" strokeWidth={2.5} className={`${iconSizes[size]} text-accent-500 dark:text-accent-700 drop-shadow-sm`} />
      </div>

      {/* Loading spinner and clear button */}
      {trailingCount > 0 && (
        <div className={`absolute inset-y-0 right-0 ${trailingPadding[size]} flex items-center gap-1 z-10`}>
          {loading && <Spinner size="sm" className="!w-5 !h-5 text-accent-600 dark:text-accent-500" />}
          {value && (
            <button
              type="button"
              onClick={clear}
              aria-label={t('common.clear')}
              title={t('common.clear')}
              className="p-1.5 rounded-full text-muted-foreground hover:text-foreground hover:bg-slate-200/70 dark:hover:bg-white/10 transition-colors"
            >
              <Icon name="close" className={iconSizes[size]} />
            </button>
          )}
        </div>
      )}
    </div>
  );
};
