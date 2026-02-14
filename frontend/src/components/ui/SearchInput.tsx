// src/components/ui/SearchInput.tsx
import React from 'react';

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  onFocus?: () => void;
  onClear?: () => void;
  autoFocus?: boolean;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  showClearButton?: boolean;
  loading?: boolean;
}

export const SearchInput: React.FC<SearchInputProps> = ({
  value,
  onChange,
  placeholder = 'Search...',
  onFocus,
  onClear,
  autoFocus = false,
  size = 'md',
  className = '',
  showClearButton = false,
  loading = false,
}) => {
  const sizeClasses = {
    sm: 'pl-10 pr-4 py-2.5 text-sm',
    md: 'pl-12 pr-4 py-3 text-base',
    lg: 'pl-16 pr-16 py-4 text-lg',
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

  return (
    <div className={`relative ${className}`}>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onFocus}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className={`w-full ${sizeClasses[size]} glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-red-600 focus:border-transparent transition-all duration-300 ${size === 'lg' ? 'shadow-lg' : ''}`}
        aria-label="search"
      />
      
      {/* Search icon */}
      <div className={`absolute inset-y-0 left-0 ${iconPadding[size]} flex items-center pointer-events-none z-10`}>
        <svg 
          className={`${iconSizes[size]} text-blue-500 dark:text-red-700 drop-shadow-sm`} 
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24" 
          strokeWidth="2.5"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>

      {/* Loading spinner */}
      {loading && (
        <div className="absolute inset-y-0 right-0 pr-4 flex items-center z-10">
          <svg className="animate-spin w-5 h-5 text-blue-600 dark:text-red-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
        </div>
      )}

      {/* Clear button */}
      {showClearButton && value && onClear && !loading && (
        <button
          onClick={onClear}
          className="absolute inset-y-0 right-0 pr-3 flex items-center text-muted-foreground hover:text-foreground z-10 transition-colors"
          type="button"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
};