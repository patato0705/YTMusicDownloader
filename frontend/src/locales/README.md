# Translating

Every text the app shows lives in one JSON file per language: `en.json` (the reference), `fr.json`, and so on. A key like `album.download` names a text; the value is what's shown.

Many values are a word or two (`"Back"`, `"Queued"`, `"Clear"`), and the English alone doesn't say what they're for. **[`notes/keys.json`](notes/keys.json) says where those appear**: a button, a badge, a column header, a screen reader label, and what fills their `{placeholders}`. A note on a group (`"mediaCard.status"`) covers every key in it. Read the note before translating a short text.

## Adding a language

1. Copy `en.json` to `<code>.json`, where `<code>` is the language's [ISO 639-1 code](https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes) (`es`, `pt`, `ja`, `ru`, `zh`, `ar`...).
2. Add it to `SUPPORTED_LOCALES` in [`../config/i18n.ts`](../config/i18n.ts), with its name in the language itself (`Español`, `日本語`) and a flag.
3. Translate the values. Leave the keys as they are.
4. From `frontend/`, run `npm test`. It checks that your file has every key, the same `{placeholders}`, and the plural forms your language needs (below), and names whatever is missing.

## Placeholders

`{name}`, `{count}`, `{date}`... are filled in by the app. Keep them exactly as written, but move them wherever your sentence needs them.

The app formats values for your language before they're filled in:

- Dates and times (`{date}`, `{time}`, `{when}`) come already formatted.
- Lists (`{names}`, `{charts}`, `{countries}`, `{days}`) come already joined with your language's words, like "A, B and C".
- `{formatted}` is a number with your language's thousand separators. Use it where it's offered, rather than `{count}`.

`{error}` is a technical message from YouTube or the downloader, and stays in English.

## Plural forms

A text with `{count}` can have a variant for each plural form of your language: `key_one`, `key_few`... The app picks the variant matching the count, using the [Unicode plural rules](https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html). The plain key is the form for every other count.

| Language | Variants to add next to the plain key |
| --- | --- |
| English, Spanish, Portuguese | `_one` (1) |
| French | `_one` (0 and 1) |
| Japanese, Chinese | none: the plain key is used for every count |
| Russian | `_one` (1, 21, 31...), `_few` (2-4, 22-24...), `_many` (0, 5-20, 25-30...). The plain key is only used for fractions. |
| Arabic | `_zero`, `_one`, `_two`, `_few` (3-10), `_many` (11-99) |

A file copied from `en.json` starts with English's `_one` variants. Delete them for Japanese and Chinese. Wherever English has a `_one` variant, your file needs all of its own variants, even if they repeat the same text. A variant may spell out the number ("an hour") only when it covers a single count. Russian `_one` also covers 21 and 31, so it has to show `{count}`. The tests check both.

## Words to keep consistent

| English | What it means here |
| --- | --- |
| follow (an artist) | Download all its releases and watch for new ones. Not a social media follow. |
| like (an artist) | The heart: personal, it feeds the recommendations. Different from follow. |
| track, song | One piece of music. French uses "titre" everywhere. |
| release | An album, a single or an EP. |
| chart | YouTube Music's weekly top artists of a country. Use the word YouTube Music uses in your language (French keeps "chart"). |
| library | Everything followed or downloaded on this server. |
| excluded, kept out | Deleted or unfollowed by hand: charts and playlists won't bring it back. |
| sync, scan | Checking YouTube Music again for changes. |
| queued | Waiting its turn to download. |
| instance | This server: the app is self-hosted. |
| sign in, sign out | Not "log in". |

Keep these names as they are: YouTube Music, YouTube, LRCLIB, MusicBrainz, Deezer, Jellyfin, M3U, NFO, LRC, `cookies.txt`, and environment variables like `TZ` and `DOWNLOAD_WORKERS`.

## Style

- **Labels other texts mention.** Some texts name a button or a page: "Download album on its page", "Admin panel > Charts", "the Lyrics column". Use your exact translation of that label there too. The notes point these out.
- **Capitals.** English uses sentence case ("Delete artist"). Follow your own language's rules, not the English capitals.
- **Address the user** in one register throughout. French uses "vous".
- **Punctuation** follows your language: French puts a space before `: ; ? !` and uses `« »`. Use your own quotation marks too («», 「」, “”...). Write "…" rather than "...".
- **Length.** Buttons, badges and column headers are narrow, so keep them short. The notes say where space is tight.

## Right-to-left languages

The layout doesn't support right-to-left text yet. An Arabic translation is welcome, but it will only look right once the layout is mirrored. Mention it in your pull request.
