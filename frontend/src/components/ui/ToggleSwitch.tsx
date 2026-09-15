// src/components/ui/ToggleSwitch.tsx
import React from 'react';

interface ToggleSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  /** Text shown next to the switch (also used as the accessible name). */
  label?: string;
  className?: string;
}

export const ToggleSwitch: React.FC<ToggleSwitchProps> = ({
  checked,
  onChange,
  disabled = false,
  label,
  className = '',
}) => {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      disabled={disabled}
      className={`inline-flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
    >
      <span
        className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors ${
          checked ? 'bg-blue-600 dark:bg-red-600' : 'bg-slate-300 dark:bg-zinc-700'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </span>
      {label && (
        <span className={`text-xs font-medium ${checked ? 'text-foreground' : 'text-muted-foreground'}`}>
          {label}
        </span>
      )}
    </button>
  );
};
