// src/components/ui/KeepWeeksSelect.tsx
import React from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Select } from './Select';

/** The choices offered; null is never */
export const KEEP_WEEKS_OPTIONS: Array<number | null> = [null, 4, 8, 12, 26, 52];

interface KeepWeeksSelectProps {
  id?: string;
  ariaLabel?: string;
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * How long a chart's artists may be out of it before it unfollows them
 * (backend services/charts.py). A value set elsewhere (a backup, the API)
 * is offered too, so the select never shows the wrong one.
 */
export const KeepWeeksSelect: React.FC<KeepWeeksSelectProps> = ({ id, ariaLabel, value, onChange, disabled, className }) => {
  const { t } = useI18n();
  const values = KEEP_WEEKS_OPTIONS.includes(value) ? KEEP_WEEKS_OPTIONS : [...KEEP_WEEKS_OPTIONS, value];
  return (
    <Select
      id={id}
      ariaLabel={ariaLabel}
      value={value === null ? 'never' : String(value)}
      onChange={(v) => onChange(v === 'never' ? null : parseInt(v, 10))}
      disabled={disabled}
      className={className}
      options={values.map((weeks) => ({
        value: weeks === null ? 'never' : String(weeks),
        label: weeks === null ? t('charts.keepWeeks.never') : t('charts.keepWeeks.weeks', { count: weeks }),
      }))}
    />
  );
};
