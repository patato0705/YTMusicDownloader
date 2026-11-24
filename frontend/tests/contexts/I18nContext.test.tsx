import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider, useI18n } from '../../src/contexts/I18nContext';
import en from '../../src/locales/en.json';
import fr from '../../src/locales/fr.json';

const HINT = 'library.filters.hints.missingTracks';

let i18n: ReturnType<typeof useI18n>;

function Probe() {
  i18n = useI18n();
  return <p>{i18n.t('common.loading')}</p>;
}

/** Renders the provider and waits for its first strings */
async function renderI18n() {
  render(<I18nProvider><Probe /></I18nProvider>);
  await screen.findByText(/./);
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US');
});

describe('I18nProvider', () => {
  it('renders nothing until the strings are in, then the translated text', async () => {
    const { container } = render(<I18nProvider><Probe /></I18nProvider>);
    expect(container).toBeEmptyDOMElement();
    expect(await screen.findByText(en.common.loading)).toBeInTheDocument();
  });

  it("starts in the browser's language when it has it", async () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('fr-CA');
    await renderI18n();
    expect(i18n.locale).toBe('fr');
    expect(screen.getByText(fr.common.loading)).toBeInTheDocument();
  });

  it('falls back to English for a language it lacks', async () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('de-DE');
    await renderI18n();
    expect(i18n.locale).toBe('en');
  });

  it('remembers the language picked, over the browser one', async () => {
    await renderI18n();
    await act(async () => i18n.setLocale('fr'));
    expect(await screen.findByText(fr.common.loading)).toBeInTheDocument();
    expect(localStorage.getItem('locale')).toBe('fr');
    expect(document.documentElement.lang).toBe('fr');
  });

  it('ignores a stored language it lacks', async () => {
    localStorage.setItem('locale', 'xx');
    await renderI18n();
    expect(i18n.locale).toBe('en');
  });
});

describe('t', () => {
  /** `text` with its {params} filled in, to compare with t() */
  const fill = (text: string, params: Record<string, string | number>) =>
    text.replace(/\{(\w+)\}/g, (match, name) => String(params[name] ?? match));

  it('fills in {params}, leaving unknown ones as they are', async () => {
    await renderI18n();
    const text = en.library.filters.hints.missingTracks;
    expect(text).toContain('{count}');
    expect(text).toContain('{total}');
    expect(i18n.t(HINT, { count: 3, total: 10 })).toBe(fill(text, { count: 3, total: 10 }));
    expect(i18n.t(HINT, { count: 3 })).toBe(fill(text, { count: 3 }));
    expect(i18n.t(HINT, { count: 3 })).toContain('{total}');
  });

  it("shows the key of a missing translation, or tOr's fallback", async () => {
    await renderI18n();
    expect(i18n.t('no.such.key')).toBe('no.such.key');
    expect(i18n.tOr('no.such.key', 'Rock')).toBe('Rock');
    // A key leading to a group of strings isn't a translation either
    expect(i18n.t('common')).toBe('common');
  });

  it("uses the singular variant for the counts the language calls singular", async () => {
    const key = 'album.trackCount';
    await renderI18n();
    // English: 1 is singular, 0 isn't
    expect(i18n.t(key, { count: 1 })).toBe(fill(en.album.trackCount_one, { count: 1 }));
    expect(i18n.t(key, { count: 0 })).toBe(fill(en.album.trackCount, { count: 0 }));

    await act(async () => i18n.setLocale('fr'));
    await screen.findByText(fr.common.loading);
    // French: 0 and 1 are both singular
    expect(i18n.t(key, { count: 0 })).toBe(fill(fr.album.trackCount_one, { count: 0 }));
    expect(i18n.t(key, { count: 1 })).toBe(fill(fr.album.trackCount_one, { count: 1 }));
    expect(i18n.t(key, { count: 2 })).toBe(fill(fr.album.trackCount, { count: 2 }));
  });

  it('uses the plain key when there is no singular variant', async () => {
    expect(en.library.filters.hints).not.toHaveProperty('missingTracks_one');
    await renderI18n();
    expect(i18n.t(HINT, { count: 1, total: 10 })).toBe(fill(en.library.filters.hints.missingTracks, { count: 1, total: 10 }));
  });

  it('ignores a count that is not a number', async () => {
    await renderI18n();
    expect(i18n.t('album.trackCount', { count: '1' })).toBe(fill(en.album.trackCount, { count: '1' }));
  });
});

describe('useI18n', () => {
  it('refuses to work outside the provider', () => {
    // React logs the error and jsdom reports it again: both kept out of the output
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const quiet = (event: ErrorEvent) => event.preventDefault();
    window.addEventListener('error', quiet);
    try {
      expect(() => render(<Probe />)).toThrow('useI18n must be used within I18nProvider');
    } finally {
      window.removeEventListener('error', quiet);
    }
  });
});
