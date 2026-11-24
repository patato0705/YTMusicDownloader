import { describe, expect, it } from 'vitest';
import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from '../../src/config/i18n';
import notes from '../../src/locales/notes/keys.json';

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

// The plural variants I18nContext picks by count (utils/translate): the plain
// key is the "other" form
const PLURAL = /_(zero|one|two|few|many)$/;
const isVariant = (key: string) => PLURAL.test(key);
const base = (key: string) => key.replace(PLURAL, '');
const category = (key: string) => key.match(PLURAL)![1];

// Counts 0 never takes: an interval of 0 is no schedule, so French can say
// "Toutes les heures" for its singular (0 and 1) without showing the count
const NO_ZERO = ['admin.settings.schedule.every_hours', 'admin.settings.schedule.every_days'];

/** The whole numbers a key's count can be that fall in a plural category */
function countsIn(rules: Intl.PluralRules, cat: string, key: string): number[] {
  const counts: number[] = [];
  for (let n = NO_ZERO.includes(key) ? 1 : 0; n <= 1000; n++) if (rules.select(n) === cat) counts.push(n);
  return counts;
}

const reference = flatten(files[DEFAULT_LOCALE]);

describe('translation files', () => {
  it('has one for each supported language, and none other', () => {
    expect(Object.keys(files).sort()).toEqual(SUPPORTED_LOCALES.map((l) => l.code).sort());
  });

  describe.each(SUPPORTED_LOCALES.map((l) => l.code))('%s', (code) => {
    const strings = flatten(files[code]);
    const keys = Object.keys(strings);
    const rules = new Intl.PluralRules(code);

    it(`has the same keys as ${DEFAULT_LOCALE}, apart from plural variants`, () => {
      // A language may need a plural form where another doesn't (French says
      // "1 titre manquant", English "1 of 10 tracks missing" works for both)
      const main = (list: string[]) => list.filter((key) => !isVariant(key));
      const missing = main(Object.keys(reference)).filter((key) => !(key in strings));
      const extra = main(keys).filter((key) => !(key in reference));
      expect(missing, 'keys to translate').toEqual([]);
      expect(extra, 'keys no longer used').toEqual([]);
    });

    it('only has plural variants of keys it has', () => {
      expect(keys.filter((key) => isVariant(key) && !(base(key) in strings))).toEqual([]);
    });

    it('only has plural variants its language uses', () => {
      // An English "_few" is never picked: English counts are only one or other
      const own = rules.resolvedOptions().pluralCategories as string[];
      expect(keys.filter((key) => isVariant(key) && !own.includes(category(key)))).toEqual([]);
    });

    it(`has every plural form of its language wherever it or ${DEFAULT_LOCALE} needs one`, () => {
      // Russian needs "1 альбом", "2 альбома" and "5 альбомов": a key with
      // only "_one" would show the plain form for both 2 and 5. "other" is the
      // plain key, which may only take fractions (Russian) and isn't counted.
      const wholeNumbers = new Set(Array.from({ length: 1001 }, (_, n) => rules.select(n)));
      wholeNumbers.delete('other');
      const plural = new Set([...Object.keys(reference), ...keys].filter(isVariant).map(base));
      const missing = [...plural].flatMap((key) =>
        [...wholeNumbers].map((cat) => `${key}_${cat}`).filter((variant) => !(variant in strings)));
      expect(missing).toEqual([]);
    });

    it('has a text for every key', () => {
      expect(keys.filter((key) => typeof strings[key] !== 'string' || !(strings[key] as string).trim())).toEqual([]);
    });

    it(`uses the same {placeholders} as ${DEFAULT_LOCALE}`, () => {
      const wrong = keys.filter((key) => {
        const own = placeholders(strings[key] as string);
        if (isVariant(key)) {
          // A variant may spell out the count ("1 titre"), not add a value
          const allowed = placeholders(String(strings[base(key)] ?? ''));
          return own.some((name) => !allowed.includes(name));
        }
        return key in reference && own.join() !== placeholders(String(reference[key])).join();
      });
      expect(wrong).toEqual([]);
    });

    // A variant may spell out "1" or "an hour" only where its category is that
    // one count: French singulars also take 0, Russian ones 21, 31...
    it('shows {count} in plural variants that cover several counts', () => {
      const wrong = keys.filter((key) =>
        isVariant(key)
        && placeholders(String(strings[base(key)] ?? '')).includes('count')
        && !placeholders(strings[key] as string).includes('count')
        && countsIn(rules, category(key), base(key)).length > 1);
      expect(wrong).toEqual([]);
    });
  });
});

describe('translator notes (locales/notes/keys.json)', () => {
  it('are about keys, or groups of keys, that exist', () => {
    // A note names a key, or a group: "mediaCard.status" covers mediaCard.status.*
    const keys = Object.keys(reference);
    const stale = Object.keys(notes).filter((note) => !keys.some((key) => key === note || key.startsWith(`${note}.`)));
    expect(stale, 'notes whose keys are gone').toEqual([]);
  });

  it('all say something', () => {
    expect(Object.entries(notes).filter(([, note]) => typeof note !== 'string' || !note.trim())).toEqual([]);
  });
});
