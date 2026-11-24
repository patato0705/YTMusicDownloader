// src/utils/translate.ts

export type Translations = Record<string, any>;
export type Params = Record<string, string | number>;

/** The string at a dotted key ("auth.login.title"), or undefined */
function lookup(translations: Translations, key: string): string | undefined {
  let value: any = translations;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object' || !(part in value)) return undefined;
    value = value[part];
  }
  return typeof value === 'string' ? value : undefined;
}

/**
 * The text of `key` with its {param}s filled in, or undefined when it has none.
 *
 * With a numeric `count` param, the key's variant for that count's plural
 * category is used when there is one: "_one" (1 in English; 0 and 1 in
 * French), "_few" (2-4, 22-24... in Russian), "_zero", "_two", "_many". The
 * plain key is the "other" form, and stands in for a missing variant.
 */
export function translate(
  translations: Translations,
  pluralRules: Intl.PluralRules,
  key: string,
  params?: Params,
): string | undefined {
  const count = params?.count;
  const category = typeof count === 'number' ? pluralRules.select(count) : 'other';
  const variant = category === 'other' ? undefined : lookup(translations, `${key}_${category}`);
  const value = variant ?? lookup(translations, key);
  if (value === undefined || !params) return value;
  return value.replace(/\{(\w+)\}/g, (match, param) => (param in params ? String(params[param]) : match));
}
