# backend/downloader/cover.py
"""Image files: downloading covers and artist pictures, moving them into place."""
from __future__ import annotations
import logging
import shutil
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("downloader.cover")


def download_image(url: str, dest: Path, timeout: float = 30) -> bool:
    """
    Download url to dest, through a temp file next to it so a failed
    download never leaves half a file. Returns whether it was saved.
    """
    temp = dest.with_name(f".{dest.name}.part")
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp.write_bytes(response.content)
        temp.replace(dest)
        dest.chmod(0o644)
        return True
    except Exception as e:
        logger.error("Failed to download %s to %s: %s", url, dest, e)
        temp.unlink(missing_ok=True)
        return False


def move_file(src: Path, dst: Path) -> Optional[Path]:
    """Move src to dst (creating its folder). Returns dst, or None if src is missing or the move failed."""
    if not src.exists():
        return None
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        return Path(shutil.move(str(src), str(dst)))
    except OSError:
        logger.exception("Failed to move %s -> %s", src, dst)
        return None
