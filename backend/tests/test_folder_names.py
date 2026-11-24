"""
Artist and album folder names: never ".", ".." or a path.

Deleting an artist removes its folder recursively, so a folder named ".."
would take MUSIC_DIR's parent with it. Names come from YouTube Music, so
anything an uploader can type has to come out as one plain folder.
"""
from __future__ import annotations

import logging

import pytest

from backend import config
from backend.db import SessionLocal
from backend.downloader.core import MAX_NAME_BYTES, fit_name, safe_name
from backend.models import Album, Artist
from backend.services import folders


@pytest.mark.parametrize("name", [None, "", "   ", ".", "..", "...", "/", "../..", "*?<>|"])
def test_names_with_nothing_usable_are_unknown(name):
    assert safe_name(name) == "Unknown"


def test_names_keep_no_path_separator():
    assert safe_name("AC/DC") == "ACDC"
    assert safe_name("..\\..\\etc") == "....etc"
    assert safe_name("a\0b") == "ab"


def test_cutting_a_long_name_never_leaves_only_dots():
    # safe_name lets this through (it has a letter), and the cut to 255
    # bytes keeps the dots and the spaces, which the strip then removes
    name = ".." + " " * (MAX_NAME_BYTES - 2) + "x"
    assert safe_name(name) == name
    assert fit_name(name) == "Unknown"
    # The same with room left for a " (2)" suffix
    assert fit_name(".." + " " * (MAX_NAME_BYTES - 6) + "x", reserve=4) == "Unknown"


def test_cutting_a_long_name_fits_the_filesystem():
    assert fit_name("a" * 300) == "a" * MAX_NAME_BYTES
    assert len(fit_name("a" * 300, reserve=4).encode()) == MAX_NAME_BYTES - 4
    # Never half a character: "é" takes two bytes, 255 is odd
    assert fit_name("é" * 200) == "é" * 127
    # Empty stays empty, for callers with their own fallback
    assert fit_name("") == ""


@pytest.mark.parametrize("stored", [".", "..", "a/b", "../music", "a\0b"])
def test_a_stored_folder_that_isnt_plain_is_never_used(stored):
    # Deleting an artist or album removes the folder these give
    artist = Artist(id="a", name="Artist", folder=stored)
    assert folders.existing_artist_dir(artist) is None
    assert folders.existing_album_dir(Album(id="b", title="Album", folder=stored, artist=None)) is None
    assert folders.existing_album_dir(
        Album(id="c", title="Album", folder="Album", artist=artist)
    ) is None


def test_plain_folders_are_inside_the_music_folder():
    artist = Artist(id="a", name="Artist", folder="Artist")
    assert folders.existing_artist_dir(artist) == config.MUSIC_DIR / "Artist"
    assert folders.existing_album_dir(Album(id="b", title="Album", folder="Album", artist=artist)) == (
        config.MUSIC_DIR / "Artist" / "Album"
    )
    assert folders.existing_album_dir(Album(id="c", title="Album", folder="Album", artist=None)) == (
        config.MUSIC_DIR / folders.NO_ARTIST / "Album"
    )
    # Nothing written yet: no folder
    assert folders.existing_artist_dir(Artist(id="d", name="New", folder=None)) is None


# The tests below write rows: `client` starts the app, which creates the schema

def test_a_stored_dot_dot_folder_is_named_again(client, caplog):
    """A row named before fit_name checked its cut (or edited by hand) gets a plain folder at its next write."""
    with SessionLocal() as session:
        artist = Artist(id="test-folder-dotdot", name="Dots", folder="..")
        session.add(artist)
        session.flush()

        with caplog.at_level(logging.WARNING, logger="services.folders"):
            path = folders.artist_dir(session, artist)

        assert path == config.MUSIC_DIR / "Dots"
        assert artist.folder == "Dots"
        assert "unusable folder name '..'" in caplog.text
        session.rollback()


def test_namesakes_get_their_own_folder(client):
    with SessionLocal() as session:
        first = Artist(id="test-folder-1", name="Same Name")
        second = Artist(id="test-folder-2", name="same name")
        session.add_all([first, second])
        session.flush()

        assert folders.artist_dir(session, first) == config.MUSIC_DIR / "Same Name"
        # Compared ignoring case, as on a Windows or macOS share
        assert folders.artist_dir(session, second) == config.MUSIC_DIR / "same name (2)"
        session.rollback()
