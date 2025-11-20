# downloader/cover.py
from __future__ import annotations
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import requests

logger = logging.getLogger("downloader.cover")
if not logging.getLogger().handlers:
    import sys, logging as _logging
    _logging.basicConfig(stream=sys.stderr, level=os.environ.get("LOG_LEVEL", "INFO"))

# Try import Pillow
try:
    from PIL import Image  # type: ignore
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


def select_best_thumbnail_url(candidates: Iterable[Union[str, Dict[str, Any]]]) -> Optional[str]:
    """
    Choisit une URL 'meilleure' parmi candidates.
    candidates: iterable de str ou dict (avec clé 'url' ou 'thumbnail' ou nested thumbnail).
    Stratégie:
      - si dicts avec width/height, choisir le plus grand width
      - sinon, retourner la dernière url plausible trouvée
    """
    thumbs: List[Dict[str, Optional[Any]]] = []
    last_url: Optional[str] = None

    for it in candidates or []:
        if it is None:
            continue

        # cas simple : string
        if isinstance(it, str):
            last_url = it
            thumbs.append({"url": it, "width": None, "height": None})
            continue

        # cas dict : essayer d'extraire url,width,height
        if isinstance(it, dict):
            url = it.get("url") or it.get("thumbnail") or None
            if isinstance(url, dict):
                # nested thumbnail object
                url = url.get("url") or None

            width: Optional[int] = None
            height: Optional[int] = None

            w = it.get("width") or it.get("w")
            if w is not None:
                try:
                    width = int(w)
                except Exception:
                    width = None

            h = it.get("height") or it.get("h")
            if h is not None:
                try:
                    height = int(h)
                except Exception:
                    height = None

            if isinstance(url, str):
                last_url = url
                thumbs.append({"url": url, "width": width, "height": height})

    # préférer la plus grande width connue
    best: Optional[str] = None
    best_w = -1
    for t in thumbs:
        w = t.get("width")
        if isinstance(w, int) and w > best_w:
            candidate_url = t.get("url")
            if isinstance(candidate_url, str):
                best = candidate_url
                best_w = w

    if best is not None:
        return best
    return last_url


def _write_bytes_to_path(content: bytes, dest: Union[str, Path]) -> Path:
    p = Path(str(dest))
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(content)
    return p


def save_cover_from_url(url: str, dest: Union[str, Path], timeout: float = 12.0) -> Optional[Path]:
    """
    Télécharge l'image depuis url et la convertit en JPEG si nécessaire.
    Retourne Path vers le fichier créé ou None en cas d'échec.
    """
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        content = r.content
    except Exception:
        logger.exception("Failed to download cover %s", url)
        return None

    destp = Path(str(dest))
    destp.parent.mkdir(parents=True, exist_ok=True)

    # Attempt to write directly if content-type claims jpeg/png
    ctype = ""
    try:
        ctype = (r.headers.get("content-type") or "").lower()
    except Exception:
        pass

    # If JPEG/PNG, write as-is but ensure .jpg extension
    try:
        if "jpeg" in ctype or "jpg" in ctype or "png" in ctype:
            # ensure extension .jpg
            final = destp.with_suffix(".jpg")
            with open(final, "wb") as fh:
                fh.write(content)
            return final
    except Exception:
        logger.debug("Direct write failed, will try conversion", exc_info=True)

    # Try Pillow conversion to JPEG
    if _HAS_PIL:
        try:
            bio = tempfile.SpooledTemporaryFile()
            bio.write(content)
            bio.seek(0)
            img = Image.open(bio).convert("RGB")
            final = destp.with_suffix(".jpg")
            img.save(final, format="JPEG", quality=85)
            return final
        except Exception:
            logger.debug("Pillow conversion failed", exc_info=True)

    # Last resort: use ffmpeg to convert
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmpf:
            tmpf.write(content)
            tmpname = tmpf.name
        final = destp.with_suffix(".jpg")
        cmd = ["ffmpeg", "-y", "-i", tmpname, str(final)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            os.unlink(tmpname)
        except Exception:
            pass
        return final
    except Exception:
        logger.exception("ffmpeg conversion failed for cover %s", url)
        return None


# alias kept for compatibility
save_and_convert_cover = save_cover_from_url


def _move_file(src: Union[str, Path], dst: Union[str, Path]) -> Optional[Path]:
    s = Path(str(src))
    d = Path(str(dst))
    if not s.exists():
        return None
    d.parent.mkdir(parents=True, exist_ok=True)
    try:
        moved = shutil.move(str(s), str(d))
        return Path(str(moved))
    except Exception:
        try:
            shutil.copyfile(str(s), str(d))
            try:
                s.unlink(missing_ok=True)
            except Exception:
                pass
            return d
        except Exception:
            logger.exception("Failed to move or copy %s -> %s", s, d)
            return None


def move_cover_if_exists(src: Union[str, Path], dst: Union[str, Path]) -> Optional[Path]:
    """
    Déplace (ou copie) src vers dst si src existe. Retourne le Path de dst ou None.
    """
    try:
        return _move_file(src, dst)
    except Exception:
        logger.exception("move_cover_if_exists failed %s -> %s", src, dst)
        return None


# Generic name used in other modules
move_if_exists = move_cover_if_exists