# backend/downloader/__init__.py
from __future__ import annotations

"""
Package downloader: réexporte les sous-modules et quelques fonctions utilitaires
pour permettre des accès comme:

    import backend.downloader as downloader
    downloader.core.download_track_by_videoid(...)
    downloader.lyrics.get_synced_lyrics(...)

Réexporter des fonctions courantes (niveaux package) est optionnel mais pratique.
"""

# import des sous-modules (les rendre accessibles via `downloader.core`, etc.)
from . import core
from . import cover
from . import metadata
from . import embed

# fonctions utilitaires fréquemment utilisées — expose-les au niveau du package
# (optionnel mais pratique pour tasks.py et autres)
try:
    download_track_by_videoid = core.download_track_by_videoid
except Exception:
    # si la fonction est manquante, on évite l'import au moment du chargement
    download_track_by_videoid = None

try:
    select_best_thumbnail_url = cover.select_best_thumbnail_url
except Exception:
    select_best_thumbnail_url = None

# contrôle public du package
__all__ = [
    "core",
    "cover",
    "metadata",
    "embed",
    "download_track_by_videoid",
    "select_best_thumbnail_url",
]