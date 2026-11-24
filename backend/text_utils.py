# backend/text_utils.py
from __future__ import annotations
import re
import unicodedata
from typing import Optional

# What every YouTube video id (and so every Track.id) looks like
VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]{11}$"
_VIDEO_ID_RE = re.compile(VIDEO_ID_PATTERN)


def is_video_id(value: Optional[str]) -> bool:
    # fullmatch: "$" alone would let a trailing newline through
    return bool(value) and _VIDEO_ID_RE.fullmatch(value) is not None


def fold(text: Optional[str]) -> str:
    """
    Text for loose comparison: case, accents and punctuation ignored,
    spacing collapsed. "Destinée, Vol. 2" -> "destinee vol 2". Letters of
    any script are kept, so two titles in Japanese don't both fold to "".
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


# What only a video's title adds to its song's: "(Official Music Video)",
# "[Clip officiel]", "(Lyrics)", "(Audio)"...
_VIDEO_DECORATION = set(
    "official officiel officielle music musical video videoclip clip lyric lyrics audio "
    "visualizer visualiser hd hq 4k uhd 1080p 720p mv m v".split()
)
# Not "with": "(With You)" is a title as often as a credit
_FEATURING = re.compile(r"^(?:feat|ft|featuring)\b")
_BRACKETED = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]")
# An unbracketed "ft. X" / "feat. X": up to the end, or the next bracket
_LOOSE_FEATURING = re.compile(r"\s(?:feat|ft|featuring)\.?\s[^()\[\]]*", re.IGNORECASE)
# "Artist - Title", "Artist: Title" (dashes of any width, written as escapes)
_ARTIST_PREFIX = re.compile(r"^\s*(.+?)\s*(?:[-:|\u2013\u2014])\s+(.+)$")


def song_title_key(title: Optional[str], artist_name: Optional[str] = None) -> str:
    """
    A title folded (see fold) without what tells a video's title from its
    song's: bracketed decoration ("(Official Video)"), featured artists
    (bracketed or not, written differently on videos and songs), and the
    artist's name in front ("Bruno Mars - Grenade"). Any other bracket is
    kept, so "Song (Live)" and "Song (Radio Edit)" stay apart from "Song".
    """
    text = title or ""
    prefix = _ARTIST_PREFIX.match(text)
    if prefix and artist_name:
        # The whole name, maybe with more artists after it ("Le Crime x
        # Leto - ..."), but not a longer word ("Museum - ..." for Muse)
        before, name = fold(prefix.group(1)), fold(artist_name)
        if before == name or before.startswith(name + " "):
            text = prefix.group(2)

    def bracket(match: "re.Match[str]") -> str:
        inner = fold(match.group(1) if match.group(1) is not None else match.group(2))
        if not inner or _FEATURING.match(inner) or set(inner.split()) <= _VIDEO_DECORATION:
            return " "
        return f" ({inner}) "

    text = _BRACKETED.sub(bracket, text)
    return fold(_LOOSE_FEATURING.sub(" ", text))
