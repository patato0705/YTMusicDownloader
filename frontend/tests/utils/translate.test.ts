import { describe, expect, it } from 'vitest';
import { translate } from '../../src/utils/translate';

// Plural variants as Russian and Arabic files will have them
const strings = {
  albums: {
    ru: '{count} альбома',
    ru_one: '{count} альбом',
    ru_few: '{count} альбома',
    ru_many: '{count} альбомов',
    ar: '{count} ألبوم',
    ar_zero: 'لا ألبومات',
    ar_one: 'ألبوم واحد',
    ar_two: 'ألبومان',
    ar_few: '{count} ألبومات',
    ar_many: '{count} ألبومًا',
  },
  plain: '{count} items',
};

describe('translate', () => {
  it("picks the variant of the count's plural category", () => {
    const ru = new Intl.PluralRules('ru');
    const say = (count: number) => translate(strings, ru, 'albums.ru', { count });
    expect([1, 21, 2, 24, 5, 11, 0].map(say)).toEqual([
      '1 альбом', '21 альбом', '2 альбома', '24 альбома', '5 альбомов', '11 альбомов', '0 альбомов',
    ]);
  });

  it('knows the six Arabic categories', () => {
    const ar = new Intl.PluralRules('ar');
    const say = (count: number) => translate(strings, ar, 'albums.ar', { count });
    expect([0, 1, 2, 3, 11, 100].map(say)).toEqual([
      'لا ألبومات', 'ألبوم واحد', 'ألبومان', '3 ألبومات', '11 ألبومًا', '100 ألبوم',
    ]);
  });

  it('falls back to the plain key for a variant it lacks', () => {
    const ru = new Intl.PluralRules('ru');
    expect(translate(strings, ru, 'plain', { count: 3 })).toBe('3 items');
  });

  it('is undefined for a missing key', () => {
    expect(translate(strings, new Intl.PluralRules('en'), 'no.such.key')).toBeUndefined();
  });
});
