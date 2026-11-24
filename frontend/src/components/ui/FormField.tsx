// src/components/ui/FormField.tsx
import React from 'react';
import { Icon } from './icons';

/** Classes of a form's text and password inputs, outlined in red while `error` is set */
export function inputClass(error?: string): string {
  return `w-full px-4 py-3 glass rounded-xl border-slate-200 dark:border-white/10 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${
    error
      ? 'focus:ring-red-500 dark:focus:ring-red-600 border-red-500/50'
      : 'focus:ring-accent-500 dark:focus:ring-accent-600'
  } focus:border-transparent transition-all duration-300`;
}

interface FormFieldProps {
  /** Id of the input, which the label points at */
  id: string;
  label: string;
  error?: string;
  /** Shown under the input while there's no error */
  hint?: string;
  children: React.ReactNode;
}

/** A labelled input with its error (or hint) under it */
export const FormField: React.FC<FormFieldProps> = ({ id, label, error, hint, children }) => (
  <div>
    <label htmlFor={id} className="block text-sm font-semibold text-foreground mb-2">
      {label}
    </label>
    {children}
    {error ? (
      <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 flex items-center gap-1">
        <Icon name="warning" className="w-3.5 h-3.5 shrink-0" />
        {error}
      </p>
    ) : hint ? (
      <p className="text-xs text-muted-foreground mt-1.5">{hint}</p>
    ) : null}
  </div>
);
