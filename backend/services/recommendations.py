# backend/services/recommendations.py
"""
Artist recommendations, from YouTube Music's own similar artists ("Fans
might also like" on an artist's page).

Every artist fetch already gets them, so they're stored as they come
(store_related) -- no extra request, no third party. They refresh with the
artist syncs.

An artist is recommended for how many followed artists list it: the more,
the higher. Ties go to the one listed earlier on average, as YouTube Music
puts the most similar first. "Followed" means a full follow: the artists of
a single downloaded album aren't synced again, and one album says little
about taste. Followed artists and dismissed ones ("not interested", shared
by everyone like follows are) are left out.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Artist, ArtistSubscription, DismissedRecommendation, RelatedArtist

logger = logging.getLogger("services.recommendations")

DEFAULT_LIMIT = 18


def store_related(session: Session, artist_id: str, related: List[Dict[str, Any]]) -> None:
    """Replace an artist's similar artists with a fresh list (adapter.get_artist's "related"). No commit."""
    existing = {
        r.related_id: r
        for r in session.execute(
            select(RelatedArtist).where(RelatedArtist.artist_id == artist_id)
        ).scalars()
    }
    for position, item in enumerate(related):
        row = existing.pop(item["id"], None)
        if row is None:
            row = RelatedArtist(artist_id=artist_id, related_id=item["id"])
            session.add(row)
        row.name = item["name"][:255]
        row.thumbnail = item.get("thumbnail")
        row.position = position
    for row in existing.values():
        session.delete(row)


def _followed_ids():
    return select(ArtistSubscription.artist_id).where(
        ArtistSubscription.enabled == True,  # noqa: E712
        ArtistSubscription.mode == "full",
    )


def list_recommendations(session: Session, limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """
    The best recommendations, each with the followed artists it's similar
    to (most similar first).
    """
    followed = _followed_ids()
    rows = session.execute(
        select(RelatedArtist, Artist.name)
        .join(Artist, Artist.id == RelatedArtist.artist_id)
        .where(
            RelatedArtist.artist_id.in_(followed),
            RelatedArtist.related_id.not_in(followed),
            RelatedArtist.related_id.not_in(select(DismissedRecommendation.artist_id)),
        )
        .order_by(RelatedArtist.position, Artist.name)
    ).all()

    by_id: Dict[str, Dict[str, Any]] = {}
    for rel, source_name in rows:
        entry = by_id.setdefault(rel.related_id, {
            "id": rel.related_id,
            "name": rel.name,
            "thumbnail": rel.thumbnail,
            "positions": [],
            "similar_to": [],
        })
        entry["positions"].append(rel.position)
        entry["similar_to"].append({"id": rel.artist_id, "name": source_name})

    ranked = sorted(
        by_id.values(),
        key=lambda e: (-len(e["positions"]), sum(e["positions"]) / len(e["positions"]), e["name"].lower()),
    )
    return [
        {
            "id": e["id"],
            "name": e["name"],
            "thumbnail": e["thumbnail"],
            "count": len(e["similar_to"]),
            "similar_to": e["similar_to"],
        }
        for e in ranked[:limit]
    ]


def count_dismissed(session: Session) -> int:
    return session.execute(select(func.count()).select_from(DismissedRecommendation)).scalar_one()


def list_dismissed(session: Session) -> List[Dict[str, Any]]:
    """Dismissed artists, last dismissed first."""
    rows = session.execute(
        select(DismissedRecommendation).order_by(DismissedRecommendation.dismissed_at.desc())
    ).scalars().all()
    return [
        {
            "id": d.artist_id,
            "name": d.name,
            "thumbnail": d.thumbnail,
            "dismissed_at": d.dismissed_at.isoformat() if d.dismissed_at else None,
        }
        for d in rows
    ]


def dismiss(session: Session, artist_id: str, user_id: Optional[int]) -> bool:
    """
    Mark an artist "not interested". Idempotent. False when the artist is
    unknown here (in no similar list, not in the library). No commit.
    """
    if session.get(DismissedRecommendation, artist_id):
        return True
    rel = session.execute(
        select(RelatedArtist).where(RelatedArtist.related_id == artist_id).limit(1)
    ).scalar_one_or_none()
    artist = session.get(Artist, artist_id) if rel is None else None
    if rel is None and artist is None:
        return False
    session.add(DismissedRecommendation(
        artist_id=artist_id,
        name=rel.name if rel else artist.name,
        thumbnail=rel.thumbnail if rel else None,
        dismissed_by=user_id,
    ))
    return True


def restore(session: Session, artist_id: str) -> bool:
    """Undo a dismissal. False when it wasn't dismissed. No commit."""
    row = session.get(DismissedRecommendation, artist_id)
    if row is None:
        return False
    session.delete(row)
    return True
