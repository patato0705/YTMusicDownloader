# Security policy

## Supported versions

Only the latest release gets security fixes. A fix comes as a new release: update with `docker compose pull` and `docker compose up -d`.

## Reporting a vulnerability

Please don't open a public issue. Report it privately instead, on the repository's **Security** tab → **Report a vulnerability**, or directly:

<https://github.com/patato0705/YTMusicDownloader/security/advisories/new>

Include what you can of:

- the version (shown on `http://<your-server>:8484/api/docs`, next to the title);
- what an attacker can do, and what they need first (an account? which role? access to the network?);
- how to reproduce it.

You'll get an answer in the report itself. Once a fix is released, the advisory is published, crediting you unless you'd rather not be named.

## Scope

In scope: this repository's code and the Docker image it publishes.

Out of scope, to report upstream instead: vulnerabilities in yt-dlp, ytmusicapi or another dependency itself (a dependency used unsafely by this app is in scope).
