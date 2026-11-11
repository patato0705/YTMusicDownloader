// src/components/library/LibraryFilters.tsx
/**
 * The Library page's filter and sort controls: a Filters button opening a
 * panel (a popover from md up, a bottom sheet on phones, which also holds
 * the sort), the sort menu, and the row of picked filters under the toolbar.
 *
 * What the filters mean is in utils/libraryFilters.ts.
 */
import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../contexts/I18nContext';
import { useDropdown } from '../../hooks/useDropdown';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { formatNumber } from '../../utils';
import type { SortOrder } from '../../api/library';
import {
  FILTER_GROUPS,
  SORT_DEFAULT_ORDER,
  SORT_KEYS,
  UNKNOWN_DECADE,
  activeFilterCount,
  filterCounts,
  libraryOptionCounts,
} from '../../utils/libraryFilters';
import type {
  FilterContext,
  FilterGroup,
  FilterGroupCounts,
  FilterHint,
  FilterItems,
  FilterOptionCount,
  LibraryFilters,
  LibrarySort,
  OfferedFilters,
  SortKey,
} from '../../utils/libraryFilters';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { SearchInput } from '../ui/SearchInput';
import { Icon } from '../ui/icons';
import type { IconName } from '../ui/icons';

type Translate = ReturnType<typeof useI18n>['t'];

/** Groups shown together, a divider apart: what needs fixing, what the releases are, where they come from */
const CLUSTERS: FilterGroup[][] = [
  ['downloads', 'lyrics', 'metadata'],
  ['type', 'decade', 'genre'],
  ['source', 'follow', 'liked'],
];

/** Genres listed before "Show all"; more than this also brings a search box */
const GENRE_PREVIEW = 12;

export function filterOptionLabel(t: Translate, group: FilterGroup, value: string): string {
  if (group === 'genre') return value;
  if (group === 'decade') {
    return value === UNKNOWN_DECADE
      ? t('library.filters.options.decade.unknown')
      : t('library.filters.options.decade.value', { decade: value });
  }
  return t(`library.filters.options.${group}.${value}`);
}

export function filterHintText(t: Translate, hint: FilterHint): string {
  const { key, ...params } = hint;
  return t(`library.filters.hints.${key}`, params);
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Keyboard focus for a menu portaled to the end of <body>: moved into it when
 * it opens (`initial` picks where), and back to its button when it closes,
 * unless the focus went somewhere else in the meantime.
 */
function useMenuFocus(
  open: boolean,
  menuRef: RefObject<HTMLElement>,
  buttonRef: RefObject<HTMLElement>,
  initial: (menu: HTMLElement) => HTMLElement | null,
) {
  const initialRef = useRef(initial);
  initialRef.current = initial;
  useEffect(() => {
    const menu = menuRef.current;
    if (!open || !menu) return;
    initialRef.current(menu)?.focus({ preventScroll: true });
    const button = buttonRef.current;
    return () => {
      if (document.activeElement === document.body) button?.focus({ preventScroll: true });
    };
  }, [open, menuRef, buttonRef]);
}

/** Tab and Shift+Tab go around a popover's controls instead of leaving it for the end of the page */
function keepTabInside(event: React.KeyboardEvent<HTMLElement>) {
  if (event.key !== 'Tab') return;
  const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE));
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const current = document.activeElement;
  if (event.shiftKey && (current === first || current === event.currentTarget)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && current === last) {
    event.preventDefault();
    first.focus();
  }
}

// ============================================================================
// SORT
// ============================================================================

interface SortControlProps {
  sort: LibrarySort;
  onChange: (sort: LibrarySort) => void;
  className?: string;
}

const ORDERS: SortOrder[] = ['asc', 'desc'];
const orderIcon = (order: SortOrder) => (order === 'asc' ? 'sortAsc' : 'sortDesc');
const orderLabel = (t: Translate, key: SortKey, order: SortOrder) => t(`library.sort.order.${key}.${order}`);

/** Picking another key starts it in its usual order (newest first for dates); the same key keeps its order */
const withKey = (sort: LibrarySort, key: SortKey): LibrarySort =>
  ({ key, order: key === sort.key ? sort.order : SORT_DEFAULT_ORDER[key] });

const MenuHeading: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="px-4 pt-1 pb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{children}</div>
);

interface MenuItemProps {
  checked: boolean;
  icon?: IconName;
  onClick: () => void;
  children: React.ReactNode;
}

const MenuItem: React.FC<MenuItemProps> = ({ checked, icon, onClick, children }) => (
  <button
    type="button"
    role="menuitemradio"
    aria-checked={checked}
    onClick={onClick}
    className={`w-full flex items-center gap-3 px-4 py-2 text-sm text-left transition-colors hover:bg-slate-100 dark:hover:bg-white/5 focus:outline-none focus-visible:bg-slate-100 dark:focus-visible:bg-white/10 ${
      checked ? 'font-medium text-accent-700 dark:text-accent-300' : 'text-foreground'
    }`}
  >
    {icon && <Icon name={icon} className="w-4 h-4 shrink-0" />}
    <span className="flex-1 min-w-0 truncate">{children}</span>
    {checked && <Icon name="check" strokeWidth={2.5} className="w-4 h-4 shrink-0" />}
  </button>
);

/**
 * The sort as a button saying both what it sorts by and which way ("Name",
 * "A to Z"), opening a menu with the keys and the two orders of the current one
 */
export const SortControl: React.FC<SortControlProps> = ({ sort, onChange, className = '' }) => {
  const { t } = useI18n();
  const dropdown = useDropdown('left', 8, { inPage: true });
  const { open, menuRef, buttonRef } = dropdown;
  const keyLabel = t(`library.sort.keys.${sort.key}`);
  const currentOrder = orderLabel(t, sort.key, sort.order);

  // Opening puts the focus on the current key
  useMenuFocus(open, menuRef, buttonRef, (menu) => menu.querySelector<HTMLElement>('[aria-checked="true"]'));

  const onMenuKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role=menuitemradio]') ?? []);
    const index = items.indexOf(document.activeElement as HTMLElement);
    const step = event.key === 'ArrowDown' ? 1 : items.length - 1;
    items[(index + step) % items.length]?.focus();
  };

  const pick = (next: LibrarySort) => {
    onChange(next);
    dropdown.setOpen(false);
  };

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={dropdown.toggle}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('library.sort.button', { key: keyLabel, order: currentOrder })}
        className={`flex items-center gap-3 glass rounded-2xl pl-3.5 pr-3 py-1.5 text-left transition-colors duration-200 hover:bg-slate-100 dark:hover:bg-white/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 ${
          open ? '!border-accent-500/50' : ''
        } ${className}`}
      >
        <Icon name={orderIcon(sort.order)} className="w-5 h-5 shrink-0 text-accent-600 dark:text-accent-400" />
        <span className="flex-1 min-w-0 leading-tight">
          <span className="block text-sm font-medium text-foreground truncate">{keyLabel}</span>
          <span className="block text-xs text-muted-foreground truncate">{currentOrder}</span>
        </span>
        <Icon name="chevronDown" className={`w-4 h-4 shrink-0 text-muted-foreground transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* In the page, scrolling with it: z-40 passes it under the navbar's z-50 like the page */}
      {dropdown.mounted && createPortal(
        <div
          ref={menuRef}
          role="menu"
          aria-label={t('library.sort.label')}
          onKeyDown={onMenuKeyDown}
          className={`absolute z-40 w-64 glass-chrome rounded-2xl shadow-2xl py-2 ${dropdown.menuMotion}`}
          style={dropdown.menuStyle}
        >
          <MenuHeading>{t('library.sort.label')}</MenuHeading>
          {SORT_KEYS.map((key) => (
            <MenuItem key={key} checked={key === sort.key} onClick={() => pick(withKey(sort, key))}>
              {t(`library.sort.keys.${key}`)}
            </MenuItem>
          ))}
          <div className="my-2 border-t border-slate-200/70 dark:border-white/10" />
          <MenuHeading>{t('library.sort.orderLabel')}</MenuHeading>
          {ORDERS.map((order) => (
            <MenuItem key={order} checked={order === sort.order} icon={orderIcon(order)} onClick={() => pick({ ...sort, order })}>
              {orderLabel(t, sort.key, order)}
            </MenuItem>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
};

/** The same choices laid out for the filter sheet: the keys as chips, the order as a two-way switch */
const SortOptions: React.FC<Omit<SortControlProps, 'className'>> = ({ sort, onChange }) => {
  const { t } = useI18n();
  return (
    <div className="space-y-3">
      <div role="radiogroup" aria-label={t('library.sort.label')} className="flex flex-wrap gap-2">
        {SORT_KEYS.map((key) => (
          <OptionChip
            key={key}
            radio
            label={t(`library.sort.keys.${key}`)}
            selected={key === sort.key}
            onClick={() => onChange(withKey(sort, key))}
          />
        ))}
      </div>
      <div role="radiogroup" aria-label={t('library.sort.orderLabel')} className="flex gap-1 p-1 rounded-2xl bg-slate-100 dark:bg-white/5">
        {ORDERS.map((order) => {
          const selected = order === sort.order;
          return (
            <button
              key={order}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange({ ...sort, order })}
              className={`flex-1 min-w-0 min-h-10 flex items-center justify-center gap-2 px-3 rounded-xl text-sm font-medium transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 ${
                selected
                  ? 'bg-white dark:bg-white/15 text-accent-700 dark:text-white shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icon name={orderIcon(order)} className="w-4 h-4 shrink-0" />
              <span className="truncate">{orderLabel(t, sort.key, order)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

// ============================================================================
// PANEL
// ============================================================================

interface OptionChipProps {
  label: string;
  /** Results picking it gives */
  count?: number;
  selected: boolean;
  /** One choice of several (a radio) rather than a toggle */
  radio?: boolean;
  onClick: () => void;
}

/** A filter value to pick, with how many results picking it gives; also the sort keys in the sheet */
const OptionChip: React.FC<OptionChipProps> = ({ label, count, selected, radio = false, onClick }) => {
  const { formatLocale } = useI18n();
  // Nothing to find with it, unless it's picked (then it must stay removable)
  const disabled = count === 0 && !selected;

  return (
    <button
      type="button"
      role={radio ? 'radio' : undefined}
      aria-checked={radio ? selected : undefined}
      aria-pressed={radio ? undefined : selected}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 min-h-10 md:min-h-8 px-3 rounded-full border text-sm transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 disabled:opacity-40 disabled:cursor-not-allowed ${
        selected
          ? 'bg-accent-600 border-accent-600 text-white shadow-sm hover:bg-accent-700'
          : 'border-slate-200 dark:border-white/10 text-foreground hover:bg-slate-100 dark:hover:bg-white/5 disabled:hover:bg-transparent'
      }`}
    >
      {selected && <Icon name="check" strokeWidth={3} className="w-3.5 h-3.5 -ml-0.5 shrink-0" />}
      <span>{label}</span>
      {count !== undefined && (
        <span className={`text-xs tabular-nums ${selected ? 'text-white/80' : 'text-muted-foreground'}`}>
          {formatNumber(count, formatLocale)}
        </span>
      )}
    </button>
  );
};

interface GroupOptionsProps {
  group: FilterGroup;
  options: FilterOptionCount[];
  picked: string[];
  onToggle: (group: FilterGroup, value: string) => void;
}

const GroupOptions: React.FC<GroupOptionsProps> = ({ group, options, picked, onToggle }) => {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => (
        <OptionChip
          key={option.value}
          label={filterOptionLabel(t, group, option.value)}
          count={option.count}
          selected={picked.includes(option.value)}
          onClick={() => onToggle(group, option.value)}
        />
      ))}
    </div>
  );
};

/** Genres can run into the hundreds: the most common first, a search box and "Show all" for the rest */
const GenreOptions: React.FC<Omit<GroupOptionsProps, 'group'>> = ({ options, picked, onToggle }) => {
  const { t } = useI18n();
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState(false);
  const many = options.length > GENRE_PREVIEW;
  const needle = query.trim().toLowerCase();

  const listed = needle
    ? options.filter((option) => option.value.toLowerCase().includes(needle))
    : expanded || !many
      ? options
      // The preview, plus any picked genre that isn't in it
      : options.filter((option, index) => index < GENRE_PREVIEW || picked.includes(option.value));

  return (
    <div className="space-y-3">
      {many && (
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t('library.filters.genreSearch')}
          size="sm"
        />
      )}
      {listed.length > 0 ? (
        <GroupOptions group="genre" options={listed} picked={picked} onToggle={onToggle} />
      ) : (
        <p className="text-sm text-muted-foreground">{t('library.filters.noGenreMatch')}</p>
      )}
      {many && !needle && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="text-sm font-medium text-accent-600 dark:text-accent-400 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 rounded"
        >
          {expanded ? t('library.filters.showFewerGenres') : t('library.filters.showAllGenres', { count: options.length })}
        </button>
      )}
    </div>
  );
};

interface FilterPanelProps {
  groups: FilterGroupCounts[];
  filters: LibraryFilters;
  onToggle: (group: FilterGroup, value: string) => void;
  /** Lay the groups out in two columns from sm up (the popover) */
  columns?: boolean;
}

/** Every group with its options. Options nothing in the library has are left out, then empty groups and clusters. */
const FilterPanel: React.FC<FilterPanelProps> = ({ groups, filters, onToggle, columns = false }) => {
  const { t } = useI18n();
  const byGroup = new Map(groups.map((g) => [g.group, g]));

  const clusters = CLUSTERS.map((cluster) => cluster.flatMap((group) => {
    const counts = byGroup.get(group);
    const picked = filters[group] ?? [];
    const options = counts?.options.filter((o) => o.libraryCount > 0 || picked.includes(o.value)) ?? [];
    return options.length > 0 ? [{ group, options, picked }] : [];
  })).filter((cluster) => cluster.length > 0);

  return (
    <div className="divide-y divide-slate-200/70 dark:divide-white/10">
      {clusters.map((cluster) => (
        <div key={cluster[0].group} className={`py-4 first:pt-0 last:pb-0 ${columns ? 'sm:columns-2 sm:gap-8' : ''}`}>
          {cluster.map(({ group, options, picked }) => (
            <section key={group} className="break-inside-avoid pb-4 last:pb-0">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                {t(`library.filters.groups.${group}`)}
              </h3>
              {group === 'genre'
                ? <GenreOptions options={options} picked={picked} onToggle={onToggle} />
                : <GroupOptions group={group} options={options} picked={picked} onToggle={onToggle} />}
            </section>
          ))}
        </div>
      ))}
    </div>
  );
};

// ============================================================================
// BUTTON + POPOVER / SHEET
// ============================================================================

interface LibraryFilterControlProps {
  filters: LibraryFilters;
  onToggle: (group: FilterGroup, value: string) => void;
  onClear: () => void;
  /** What the page could list right now (tab and search applied), for the option counts */
  shown: FilterItems;
  /** Everything, to leave out options nothing in the library has */
  library: FilterItems;
  context: FilterContext;
  offered: OfferedFilters;
  collator: Intl.Collator;
  /** Results the filters give now */
  resultCount: number;
  sort: LibrarySort;
  onSortChange: (sort: LibrarySort) => void;
  /** The popover opens from the button's left edge and stays within this element's sides */
  boundsRef?: RefObject<HTMLElement>;
  className?: string;
}

export const LibraryFilterControl: React.FC<LibraryFilterControlProps> = ({
  filters,
  onToggle,
  onClear,
  shown,
  library,
  context,
  offered,
  collator,
  resultCount,
  sort,
  onSortChange,
  boundsRef,
  className = '',
}) => {
  const { t, formatLocale } = useI18n();
  const wide = useMediaQuery('(min-width: 768px)');
  const dropdown = useDropdown('left', 8, { bounds: boundsRef, inPage: true, fitBelow: true });
  const { open, setOpen, menuRef, buttonRef } = dropdown;
  const titleId = useId();
  const active = activeFilterCount(filters);
  const results = t('library.filters.results', { count: resultCount, formatted: formatNumber(resultCount, formatLocale) });

  // The counts are only worked out while the panel is on screen (open, or
  // fading after closing). Those over the whole library change with the
  // library alone; the others with the picks too.
  const libraryCounts = useMemo(
    () => (dropdown.mounted ? libraryOptionCounts(library, context, offered, collator) : null),
    [dropdown.mounted, library, context, offered, collator]
  );
  const groups = useMemo(
    () => (libraryCounts ? filterCounts(shown, libraryCounts, filters, context) : []),
    [libraryCounts, shown, filters, context]
  );

  // The popover and the sheet are different panels: crossing the breakpoint
  // (a tablet turned) closes whichever is open rather than swapping it live
  const wasWide = useRef(wide);
  useEffect(() => {
    if (wasWide.current === wide) return;
    wasWide.current = wide;
    setOpen(false);
  }, [wide, setOpen]);

  // The popover takes the focus when it opens (the sheet is a Modal, which does)
  useMenuFocus(open && wide, menuRef, buttonRef, (menu) => menu);

  const clearButton = active > 0 && (
    <button
      type="button"
      onClick={onClear}
      className="shrink-0 text-sm font-medium text-accent-600 dark:text-accent-400 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 rounded"
    >
      {t('library.filters.clearAll')}
    </button>
  );

  return (
    <>
      <button
        ref={dropdown.buttonRef}
        type="button"
        onClick={dropdown.toggle}
        aria-haspopup="dialog"
        aria-expanded={dropdown.open}
        aria-label={active > 0 ? t('library.filters.buttonActive', { count: active }) : t('library.filters.button')}
        className={`shrink-0 flex items-center justify-center gap-2 glass rounded-2xl px-3.5 md:px-4 text-sm font-medium transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 ${
          active > 0 || dropdown.open
            ? 'text-accent-700 dark:text-accent-300 !border-accent-500/50'
            : 'text-foreground hover:bg-slate-100 dark:hover:bg-white/5'
        } ${className}`}
      >
        <Icon name="filter" className="w-5 h-5 shrink-0" />
        <span className="hidden md:inline">{t('library.filters.button')}</span>
        {active > 0 && (
          <span className="min-w-5 h-5 px-1.5 rounded-full bg-accent-600 text-white text-xs font-semibold tabular-nums flex items-center justify-center">
            {active}
          </span>
        )}
      </button>

      {/* Scrolls with the page and under the navbar, like the sort menu */}
      {dropdown.mounted && wide && createPortal(
        <div
          ref={dropdown.menuRef}
          role="dialog"
          aria-labelledby={titleId}
          tabIndex={-1}
          onKeyDown={keepTabInside}
          className={`absolute z-40 w-[44rem] glass-chrome rounded-2xl shadow-2xl flex flex-col overflow-hidden outline-none ${dropdown.menuMotion}`}
          style={dropdown.menuStyle}
        >
          <div className="flex items-center justify-between gap-4 px-5 py-3.5 border-b border-slate-200/70 dark:border-white/10">
            <div className="min-w-0">
              <h2 id={titleId} className="font-semibold text-foreground">{t('library.filters.title')}</h2>
              <p className="text-xs text-muted-foreground tabular-nums" aria-live="polite">{results}</p>
            </div>
            {clearButton}
          </div>
          <div className="min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-5 py-4">
            <FilterPanel groups={groups} filters={filters} onToggle={onToggle} columns />
          </div>
        </div>,
        document.body,
      )}

      {dropdown.open && !wide && (
        <Modal sheet onClose={() => dropdown.setOpen(false)} labelledBy={titleId}>
          {(close) => (
            <>
              <div className="shrink-0 px-5 pb-3 border-b border-slate-200/70 dark:border-white/10">
                {/* Says the sheet can be swiped down (useSheetDismiss) */}
                <div className="mx-auto mt-2.5 mb-2 h-1.5 w-10 rounded-full bg-slate-300 dark:bg-white/20" aria-hidden="true" />
                <div className="flex items-center justify-between gap-4">
                  <h2 id={titleId} className="text-lg font-semibold text-foreground">{t('library.filters.title')}</h2>
                  <button
                    type="button"
                    onClick={close}
                    aria-label={t('common.close')}
                    className="w-10 h-10 -mr-2 flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-white/10 transition-colors"
                  >
                    <Icon name="close" />
                  </button>
                </div>
              </div>

              <div data-sheet-scroll className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-5 py-4">
                <section className="pb-4 mb-4 border-b border-slate-200/70 dark:border-white/10">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{t('library.sort.label')}</h3>
                  <SortOptions sort={sort} onChange={onSortChange} />
                </section>
                <FilterPanel groups={groups} filters={filters} onToggle={onToggle} />
              </div>

              <div className="shrink-0 flex gap-3 px-5 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] border-t border-slate-200/70 dark:border-white/10">
                <Button variant="secondary" onClick={onClear} disabled={active === 0} className="flex-1">
                  {t('library.filters.clearAll')}
                </Button>
                <Button variant="primary" onClick={close} className="flex-[2] tabular-nums">
                  {t('library.filters.showResults', { count: resultCount, formatted: formatNumber(resultCount, formatLocale) })}
                </Button>
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  );
};

// ============================================================================
// PICKED FILTERS
// ============================================================================

interface ActiveFiltersProps {
  filters: LibraryFilters;
  onToggle: (group: FilterGroup, value: string) => void;
  onClear: () => void;
  resultCount: number;
}

/** The picked filters as removable chips; a sideways scroll on phones, wrapping from md up */
export const ActiveFilters: React.FC<ActiveFiltersProps> = ({ filters, onToggle, onClear, resultCount }) => {
  const { t, formatLocale } = useI18n();
  const picked = FILTER_GROUPS.flatMap((group) => (filters[group] ?? []).map((value) => ({ group, value })));
  if (picked.length === 0) return null;

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 min-w-0 flex items-center gap-2 overflow-x-auto no-scrollbar md:flex-wrap md:overflow-visible">
        {picked.map(({ group, value }) => {
          const label = filterOptionLabel(t, group, value);
          return (
            <button
              key={`${group}:${value}`}
              type="button"
              onClick={() => onToggle(group, value)}
              aria-label={t('library.filters.remove', { label })}
              className="shrink-0 inline-flex items-center gap-1.5 min-h-9 pl-3 pr-2 rounded-full border border-accent-500/30 bg-accent-500/10 text-sm font-medium text-accent-700 dark:text-accent-300 transition-colors hover:bg-accent-500/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
            >
              {label}
              <Icon name="close" strokeWidth={2.5} className="w-3.5 h-3.5 opacity-70" />
            </button>
          );
        })}
        <button
          type="button"
          onClick={onClear}
          className="shrink-0 min-h-9 px-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 rounded"
        >
          {t('library.filters.clearAll')}
        </button>
      </div>
      <span className="hidden md:block shrink-0 text-sm text-muted-foreground tabular-nums" aria-live="polite">
        {t('library.filters.results', { count: resultCount, formatted: formatNumber(resultCount, formatLocale) })}
      </span>
    </div>
  );
};
