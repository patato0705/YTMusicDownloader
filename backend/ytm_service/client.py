# backend/ytm_service/client.py
from __future__ import annotations
import logging
import threading
import time
from typing import Any, Dict, Optional

from ytmusicapi import YTMusic
from ytmusicapi.helpers import parse_description_runs
from ytmusicapi.navigation import (
    CAROUSEL, CAROUSEL_TITLE, DESCRIPTION_RUN_LIST, SECTION_LIST, SINGLE_COLUMN_TAB,
    TAB_CONTENT, THUMBNAILS, TITLE_TEXT, TWO_COLUMN_RENDERER, find_object_by_key, nav,
)

from ..config import HEADERS_AUTH, YTM_MAX_CONC, YTM_BACKOFF_BASE, YTM_BACKOFF_MAX

logger = logging.getLogger("ytm_service.client")


class _YTMusic(YTMusic):
    def get_artist(self, channelId: str) -> Dict[str, Any]:  # noqa: N803 (ytmusicapi's name)
        """
        An artist page, read where ytmusicapi's get_artist (1.12.3) fails:
          - a YouTube user's channel (a YouTuber credited on a video): its
            header is a musicVisualHeaderRenderer, not an artist's
            musicImmersiveHeaderRenderer, with the channel's round picture
            beside the wide banner; it has no albums or singles
          - a page with an untitled carousel (a "Watch the new music video"
            promo), which get_artist's section parser can't name

        Returns only what the adapter reads: name, description, thumbnails
        (the banner), picture (the square picture's thumbnails: the banner's
        for an artist), channel (a YouTube user's channel, not an artist: the
        user's header, and no releases) and the page's sections (albums,
        singles, related...).
        """
        response = self._send_request("browse", {"browseId": channelId.removeprefix("MPLA")})
        # Some artist pages are two-column (ytmusicapi #929)
        results = nav(response, SINGLE_COLUMN_TAB + SECTION_LIST, True)
        if results is None:
            results = nav(response, [*TWO_COLUMN_RENDERER, *TAB_CONTENT, *SECTION_LIST])
        headers = response["header"]
        header = headers.get("musicImmersiveHeaderRenderer") or headers["musicVisualHeaderRenderer"]
        banner = nav(header, THUMBNAILS, True) or []
        description_shelf = find_object_by_key(results, "musicDescriptionShelfRenderer", is_key=True)
        description, _ = parse_description_runs(nav(description_shelf or {}, DESCRIPTION_RUN_LIST, True))
        titled = [r for r in results if CAROUSEL[0] not in r or nav(r, CAROUSEL + CAROUSEL_TITLE, True)]
        sections = self.parser.parse_channel_contents(titled)
        return {
            **sections,
            "name": nav(header, TITLE_TEXT),
            # Both, as an artist page without a banner may use the user's
            # header too: what's taken for a channel is unfollowed
            "channel": "musicImmersiveHeaderRenderer" not in headers
            and not sections.get("albums") and not sections.get("singles"),
            "description": description or None,
            "thumbnails": banner,
            "picture": nav(header, ["foregroundThumbnail", "musicThumbnailRenderer", "thumbnail", "thumbnails"], True)
            or banner,
        }


# One client per process, created on first use; at most YTM_MAX_CONC calls at once
_ytm_lock = threading.Lock()
_ytm_client: Optional[YTMusic] = None
_ytm_sem = threading.BoundedSemaphore(YTM_MAX_CONC)


def _get_language() -> str:
    """The ytmusic.language setting, 'en' if it can't be read."""
    from ..db import SessionLocal
    from ..settings import get_setting
    try:
        with SessionLocal() as session:
            return str(get_setting(session, "ytmusic.language") or "en")
    except Exception:
        logger.exception("Failed to read ytmusic.language setting; falling back to 'en'")
        return "en"


def get_client() -> YTMusic:
    """
    The YTMusic instance, created on first use. HEADERS_AUTH, when set, is
    the path of a headers_auth.json to reuse an authenticated session;
    otherwise the client is anonymous.
    """
    global _ytm_client
    with _ytm_lock:
        if _ytm_client is None:
            language = _get_language()
            if HEADERS_AUTH:
                logger.info("Initializing YTMusic with headers file: %s (language=%s)", HEADERS_AUTH, language)
                _ytm_client = _YTMusic(auth=HEADERS_AUTH, language=language)
            else:
                logger.info("Initializing anonymous YTMusic client (language=%s)", language)
                _ytm_client = _YTMusic(language=language)
        return _ytm_client


def reset_client() -> None:
    """
    Invalidate the cached YTMusic client. The next call to get_client() will
    re-initialize it, picking up any changed settings (e.g. language).
    """
    global _ytm_client
    with _ytm_lock:
        _ytm_client = None
    logger.info("YTMusic client cache cleared")


def call(method_name: str, *args: Any, max_retries: int = 4, **kwargs: Any) -> Any:
    """
    Call a YTMusic method, retrying with exponential backoff (YouTube Music
    sends empty or unparseable pages at times). Raises the last error once
    out of retries; the caller decides how to report it.

        call("get_playlist", playlistId="...")
    """
    method = getattr(get_client(), method_name)
    for attempt in range(1, max_retries + 1):
        try:
            with _ytm_sem:
                return method(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries:
                raise
            backoff = min(YTM_BACKOFF_MAX, YTM_BACKOFF_BASE * (2 ** (attempt - 1)))
            logger.warning("YTMusic call %s failed (attempt %s/%s): %s, retrying in %.2fs",
                           method_name, attempt, max_retries, e, backoff)
            time.sleep(backoff)
