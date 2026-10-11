// src/components/admin/ScheduleInput.tsx
/**
 * Editor for a "schedule" setting (backend/schedules.py): every N hours/days,
 * or at a fixed time on chosen days of the week.
 *
 * Laid out like the other settings rows: ScheduleControls is the control on
 * the right (mode, then the interval or the time, then the days under them),
 * ScheduleHint the small line under the description on the left.
 */
import React, { useMemo, useRef } from 'react';
import { useI18n } from '../../contexts/I18nContext';
import { Select } from '../ui/Select';
import type { Schedule, Weekday } from '../../api/admin';

export const WEEKDAYS: Weekday[] = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;

/** t() with an "_one" variant of the key for a count of 1, when it exists. */
const useCountedT = () => {
  const { t } = useI18n();
  return (key: string, count: number, params: Record<string, string | number> = {}): string => {
    if (count === 1) {
      const one = t(`${key}_one`, { count, ...params });
      if (one !== `${key}_one`) return one;
    }
    return t(key, { count, ...params });
  };
};

/** Whether a schedule can be saved (mirrors backend validation). */
export const isValidSchedule = (value: any, min = 1): boolean => {
  if (!value || typeof value !== 'object') return false;
  if (value.mode === 'interval') return Number.isInteger(value.every) && value.every >= min;
  if (value.mode === 'fixed') {
    return TIME.test(value.time ?? '') && Array.isArray(value.days) && value.days.length > 0;
  }
  return false;
};

/** Localized weekday names, Monday first. */
const useWeekdayNames = (style: 'short' | 'long' = 'short'): Record<Weekday, string> => {
  const { formatLocale } = useI18n();
  return useMemo(() => {
    const format = new Intl.DateTimeFormat(formatLocale, { weekday: style });
    // 2024-01-01 was a Monday
    return Object.fromEntries(
      WEEKDAYS.map((day, i) => [day, format.format(new Date(2024, 0, 1 + i))]),
    ) as Record<Weekday, string>;
  }, [formatLocale, style]);
};

/** "Every 6 hours" / "Mon, Fri at 07:00": the schedule in a few words. */
export const useScheduleSummary = () => {
  const { t } = useI18n();
  const tc = useCountedT();
  const dayNames = useWeekdayNames();
  return (value: Schedule | null | undefined, unit: 'hours' | 'days' | null | undefined): string => {
    if (!value) return '';
    if (value.mode === 'interval') {
      return tc(`admin.settings.schedule.every_${unit === 'days' ? 'days' : 'hours'}`, value.every);
    }
    const days = value.days.length === 7
      ? t('admin.settings.schedule.everyDay')
      : value.days.map((d) => dayNames[d]).join(', ');
    return t('admin.settings.schedule.fixedSummary', { days, time: value.time });
  };
};

const inputClass =
  'px-3 py-2 glass rounded-xl border text-foreground focus:outline-none focus:ring-2 ' +
  'focus:ring-blue-500 dark:focus:ring-red-600';
const borderClass = (invalid: boolean) =>
  invalid ? 'border-red-500 dark:border-red-500' : 'border-slate-200 dark:border-white/10';

interface ScheduleControlsProps {
  value: Schedule;
  onChange: (value: Schedule) => void;
  unit: 'hours' | 'days';
  min?: number;
}

export const ScheduleControls: React.FC<ScheduleControlsProps> = ({ value, onChange, unit, min = 1 }) => {
  const { t } = useI18n();
  const tc = useCountedT();
  const dayNames = useWeekdayNames();
  const longDayNames = useWeekdayNames('long');
  // What each mode last held, so flipping back and forth loses nothing
  const remembered = useRef<{ interval?: Schedule; fixed?: Schedule }>({});
  remembered.current[value.mode] = value;

  const setMode = (mode: string) => {
    if (mode === value.mode || (mode !== 'interval' && mode !== 'fixed')) return;
    onChange(
      remembered.current[mode] ??
        (mode === 'fixed'
          ? { mode: 'fixed', time: '04:00', days: [...WEEKDAYS] }
          : { mode: 'interval', every: unit === 'days' ? 7 : 6 }),
    );
  };

  const toggleDay = (day: Weekday) => {
    if (value.mode !== 'fixed') return;
    const days = value.days.includes(day) ? value.days.filter((d) => d !== day) : [...value.days, day];
    onChange({ ...value, days: WEEKDAYS.filter((d) => days.includes(d)) });
  };

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-2">
        <Select
          value={value.mode}
          onChange={setMode}
          options={[
            { value: 'interval', label: t(`admin.settings.schedule.modeInterval_${unit}`) },
            { value: 'fixed', label: t('admin.settings.schedule.modeFixed') },
          ]}
          className="w-36 !py-2"
        />
        {value.mode === 'interval' ? (
          <>
            <input
              type="number"
              min={min}
              step={1}
              value={Number.isFinite(value.every) ? value.every : ''}
              onChange={(e) =>
                onChange({ mode: 'interval', every: e.target.value === '' ? NaN : Number(e.target.value) })
              }
              aria-label={t(`admin.settings.schedule.unit_${unit}`)}
              className={`w-20 text-center ${inputClass} ${borderClass(!isValidSchedule(value, min))}`}
            />
            <span className="w-14 text-sm text-muted-foreground">{tc(`admin.settings.schedule.unit_${unit}`, value.every)}</span>
          </>
        ) : (
          <input
            type="time"
            step={60}
            value={value.time}
            onChange={(e) => onChange({ ...value, time: e.target.value })}
            aria-label={t('admin.settings.schedule.timeLabel')}
            className={`w-36 ${inputClass} ${borderClass(!TIME.test(value.time))}`}
          />
        )}
      </div>

      {value.mode === 'fixed' && (
        <div className="flex flex-wrap justify-end gap-1" role="group" aria-label={t('admin.settings.schedule.daysLabel')}>
          {WEEKDAYS.map((day) => {
            const checked = value.days.includes(day);
            return (
              <button
                key={day}
                type="button"
                role="checkbox"
                aria-checked={checked}
                aria-label={longDayNames[day]}
                title={longDayNames[day]}
                onClick={() => toggleDay(day)}
                className={`h-7 min-w-[2.6rem] px-1.5 rounded-full border text-xs font-medium transition-colors ${
                  checked
                    ? 'bg-blue-500/15 text-blue-700 border-blue-500/30 dark:bg-red-500/15 dark:text-red-400 dark:border-red-500/30'
                    : 'border-slate-300/70 dark:border-white/10 text-muted-foreground hover:text-foreground'
                }`}
              >
                {dayNames[day]}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

interface ScheduleHintProps {
  settingKey: string;
  value: Schedule;
  /** Next fixed run of the saved value (from the backend), ISO */
  nextRun?: string | null;
  /** Whether `value` differs from the saved one (the next run is then unknown) */
  dirty: boolean;
  timezone?: string | null;
}

/** The small line under the description: how interval mode counts, or the next fixed run. */
export const ScheduleHint: React.FC<ScheduleHintProps> = ({ settingKey, value, nextRun, dirty, timezone }) => {
  const { t, formatLocale } = useI18n();
  const tc = useCountedT();

  let text: string | null = null;
  let warning = false;
  if (value.mode === 'interval') {
    text = Number.isFinite(value.every) ? tc(`admin.settings.keys.${settingKey}.intervalHint`, value.every) : null;
  } else if (value.days.length === 0) {
    text = t('admin.settings.schedule.noDays');
    warning = true;
  } else if (dirty) {
    text = t('admin.settings.schedule.nextRunAfterSave');
  } else if (nextRun) {
    const when = new Intl.DateTimeFormat(formatLocale, {
      weekday: 'long', hour: '2-digit', minute: '2-digit', hour12: false,
      ...(timezone ? { timeZone: timezone } : {}),
    }).format(new Date(nextRun));
    text = t('admin.settings.schedule.nextRun', { when });
  }
  if (!text) return null;
  return (
    <p className={`text-xs mt-1.5 ${warning ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground'}`}>
      {text}
    </p>
  );
};
