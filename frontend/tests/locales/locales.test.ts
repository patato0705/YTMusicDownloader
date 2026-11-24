import { describe, expect, it } from 'vitest';
import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from '../../src/config/i18n';

// Every translation file, by locale code
const files = Object.fromEntries(
  Object.entries(import.meta.glob<Record<string, unknown>>('../../src/locales/*.json', { eager: true, import: 'default' }))
    .map(([path, strings]) => [path.slice(path.lastIndexOf('/') + 1, -'.json'.length), strings]),
);

/** Dotted key -> value, for every leaf */
function flatten(tree: Record<string, unknown>, prefix = '', into: Record<string, unknown> = {}) {
  for (const [key, value] of Object.entries(tree)) {
    if (value && typeof value === 'object') flatten(value as Record<string, unknown>, `${prefix}${key}.`, into);
    else into[`${prefix}${key}`] = value;
  }
  return into;
}

const placeholders = (text: string) => [...new Set([...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort();

// The singular variant I18nContext picks for a count the language calls singular
const SINGULAR = '_one';
const base = (key: string) => key.slice(0, -SINGULAR.length);

const reference = flatten(files[DEFAULT_LOCALE]);

describe('translation files', () => {
  it('has one for each supported language, and none other', () => {
    expect(Object.keys(files).sort()).toEqual(SUPPORTED_LOCALES.map((l) => l.code).sort());
  });

  describe.each(SUPPORTED_LOCALES.map((l) => l.code))('%s', (code) => {
    const strings = flatten(files[code]);
    const keys = Object.keys(strings);

    it(`has the same keys as ${DEFAULT_LOCALE}, apart from singular variants`, () => {
      // A language may need a singular where another doesn't (French says
      // "1 titre manquant", English "1 of 10 tracks missing" works for both)
      const main = (list: string[]) => list.filter((key) => !key.endsWith(SINGULAR));
      const missing = main(Object.keys(reference)).filter((key) => !(key in strings));
      const extra = main(keys).filter((key) => !(key in reference));
      expect(missing, 'keys to translate').toEqual([]);
      expect(extra, 'keys no longer used').toEqual([]);
    });

    it('only has singular variants of keys it has', () => {
      expect(keys.filter((key) => key.endsWith(SINGULAR) && !(base(key) in strings))).toEqual([]);
    });

    it('has a text for every key', () => {
      expect(keys.filter((key) => typeof strings[key] !== 'string' || !(strings[key] as string).trim())).toEqual([]);
    });

    it(`uses the same {placeholders} as ${DEFAULT_LOCALE}`, () => {
      const wrong = keys.filter((key) => {
        const own = placeholders(strings[key] as string);
        if (key.endsWith(SINGULAR)) {
          // A singular may spell out the count ("1 titre"), not add a value
          const allowed = placeholders(String(strings[base(key)] ?? ''));
          return own.some((name) => !allowed.includes(name));
        }
        return key in reference && own.join() !== placeholders(String(reference[key])).join();
      });
      expect(wrong).toEqual([]);
    });

    // Where 0 is singular too (French), a singular that spells out "1" or
    // "une heure" would show it for a count of 0
    it.runIf(new Intl.PluralRules(code).select(0) === 'one')('shows {count} in singulars whose plural does', () => {
      // "Toutes les heures": no number to show, and 0 is no schedule anyway
      const wordOnly = ['admin.settings.schedule.every_hours_one', 'admin.settings.schedule.every_days_one'];
      const wrong = keys.filter((key) =>
        key.endsWith(SINGULAR) && !wordOnly.includes(key)
        && placeholders(String(strings[base(key)] ?? '')).includes('count')
        && !placeholders(strings[key] as string).includes('count'));
      expect(wrong).toEqual([]);
    });
  });
});
