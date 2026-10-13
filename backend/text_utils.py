# backend/text_utils.py
from __future__ import annotations
import re
import unicodedata
from typing import Optional


def fold(text: Optional[str]) -> str:
    """
    Text for loose comparison: case, accents and punctuation ignored,
    spacing collapsed. "Destinée, Vol. 2" -> "destinee vol 2". Letters of
    any script are kept, so two titles in Japanese don't both fold to "".
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())
