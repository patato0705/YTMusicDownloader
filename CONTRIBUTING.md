# Contributing

Thanks for wanting to help. Bug reports, fixes, translations and ideas are all welcome.

## Before you start

- **A bug?** Open an issue with the bug report form: the version and the log lines are what make it fixable.
- **A new feature, a new dependency, or a change in how something works?** Open an issue first, so we agree on the approach before you spend time on it.
- **A typo, a small fix or a translation?** Open a pull request directly.
- **A security problem?** Not in an issue: see [SECURITY.md](SECURITY.md).

## Setting up

The README's [Development](README.md#development) section has it all: the backend runs in Docker (built from your checkout with `docker-compose.dev.yml`), the frontend with the Vite dev server.

The backend only runs on Linux and macOS (it locks files with `fcntl`). On Windows, use Docker or WSL for it, or let CI run its tests.

## Checks

CI runs every check on each pull request (`.github/workflows/ci.yml`), so you don't have to run them all yourself. To run them locally:

```bash
# frontend, from frontend/
npm run lint
npm test
npm run build      # includes the type check

# backend, from the repository root (Linux or macOS)
pip install -r backend/requirements.txt -r backend/tests/requirements.txt
ruff check --select E9,F --target-version py314 backend
python -m pytest backend/tests

# the Docker image, from the repository root (Docker, curl and jq)
docker build -t ytmusicdownloader:test .
bash .github/scripts/docker-smoke-test.sh ytmusicdownloader:test
```

## What the code relies on

The tests enforce most of these, and the pull request template asks about the others:

- **A new or changed API route** goes in the `ACCESS` table of `backend/tests/test_access.py`, with the lowest role allowed to call it. The access decision then shows in the diff.
- **A change to `backend/models.py`** comes with a migration in `backend/migrations/versions/`: see [Database schema changes](README.md#development).
- **Text shown to users** goes in every file of `frontend/src/locales/` (`en.json`, `fr.json`, `es.json`...), with the same keys and `{placeholders}`. Don't speak one of the languages? Copy the English text into its file and say so in the pull request. When the English alone doesn't say where a text appears (a one-word button, a badge, a column header), add a line for it to `frontend/src/locales/notes/keys.json` so translators know. Translating the app? Start with [the translation guide](frontend/src/locales/README.md).
- **Security-related code** (sign-in, file paths, the thumbnail proxy, what public endpoints return) comes with a test.
- **Dependencies** stay pinned: exact versions in `backend/requirements.txt`, and `frontend/package-lock.json` committed. yt-dlp is the one exception, on purpose (see the comment in `requirements.txt`).
- **Style**: no formatter is enforced. Match the code around yours, and write comments that say why, not what.

## Commits and pull requests

Commit messages are one line, `type: what changes`, in plain words:

```
feat: filter the library by synced lyrics and instrumental tracks
fix: keep the phone tab bar clear of the iPhone home indicator
```

The types are `feat` (something new for users), `fix`, `refactor`, `docs`, `test`, `ci` and `chore` (dependencies, cleanup).

A pull request goes into `main` and is about one thing. CI has to pass before it's merged.

## Releases

Releases are made by the maintainer, from a version tag: see *Releases* in the README's [Development](README.md#development) section.

## License

By contributing, you agree that your contributions are licensed under the [GNU AGPL v3](LICENSE), like the rest of the project.
