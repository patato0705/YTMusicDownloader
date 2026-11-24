# backend/lyrics/__init__.py
"""
Lyrics providers (see base.py for what one looks like):
- lrclib: LRCLIB (lrclib.net), community-uploaded synced and plain lyrics.
  The authority: asked first, and the only one to say "instrumental"
- ytmusic: YouTube Music's own lyrics, asked only when LRCLIB has nothing
  usable (the order is jobs.tasks._download_lyrics')
"""
