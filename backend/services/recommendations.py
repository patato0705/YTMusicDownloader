# backend/services/recommendations.py
"""
Artist recommendations, from YouTube Music's own similar artists ("Fans
might also like" on an artist's page).

Every artist fetch already gets them, so they're stored as they come
(store_related) -- no extra request, no third party. They refresh with the
artist syncs.

Recommendations are personal: they come from the artists each user likes
(a heart on artists of the library; following one likes it too), not from
the library's follows, which charts and playlists bring in by the dozen
whatever anyone's taste.

An artist is recommended for how many of your liked artists list it: the
more, the higher. Ties go to the one listed earlier on average, as YouTube
Music puts the most similar first. Artists you like, those followed in full
(already downloading everything) and those you dismissed ("not
interested", also personal) are left out.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import Artist, ArtistLike, ArtistSubscription, DismissedRecommendation, RelatedArtist

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


def _liked_ids(user_id: int):
    return select(ArtistLike.artist_id).where(ArtistLike.user_id == user_id)


def _dismissed_ids(user_id: int):
    return select(DismissedRecommendation.artist_id).where(DismissedRecommendation.user_id == user_id)


def list_recommendations(session: Session, user_id: int, limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """
    The best recommendations for a user, each with the liked artists it's
    similar to (most similar first).
    """
    liked = _liked_ids(user_id)
    rows = session.execute(
        select(RelatedArtist, Artist.name)
        .join(Artist, Artist.id == RelatedArtist.artist_id)
        .where(
            RelatedArtist.artist_id.in_(liked),
            RelatedArtist.related_id.not_in(liked),
            RelatedArtist.related_id.not_in(_followed_ids()),
            RelatedArtist.related_id.not_in(_dismissed_ids(user_id)),
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


def count_liked(session: Session, user_id: int) -> int:
    return session.execute(
        select(func.count()).select_from(ArtistLike).where(ArtistLike.user_id == user_id)
    ).scalar_one()


def liked_artist_ids(session: Session, user_id: int) -> set[str]:
    return set(session.execute(_liked_ids(user_id)).scalars())


def is_liked(session: Session, user_id: int, artist_id: str) -> bool:
    return session.get(ArtistLike, (user_id, artist_id)) is not None


def like(session: Session, user_id: int, artist_id: str) -> bool:
    """
    Like an artist. Idempotent. False when the artist isn't in the library
    (no enabled subscription): its similar artists are only known once
    synced. No commit.
    """
    in_library = session.execute(
        select(ArtistSubscription.id).where(
            ArtistSubscription.artist_id == artist_id,
            ArtistSubscription.enabled == True,  # noqa: E712
        )
    ).first()
    if in_library is None:
        return False
    if not is_liked(session, user_id, artist_id):
        session.add(ArtistLike(user_id=user_id, artist_id=artist_id))
    return True


def unlike(session: Session, user_id: int, artist_id: str) -> None:
    """Idempotent. No commit."""
    row = session.get(ArtistLike, (user_id, artist_id))
    if row is not None:
        session.delete(row)


def delete_artist_likes(session: Session, artist_id: str) -> None:
    """Everyone's like of a deleted artist. No commit."""
    session.execute(delete(ArtistLike).where(ArtistLike.artist_id == artist_id))


def delete_user_data(session: Session, user_id: int) -> None:
    """A deleted user's likes and dismissals. No commit."""
    session.execute(delete(ArtistLike).where(ArtistLike.user_id == user_id))
    session.execute(delete(DismissedRecommendation).where(DismissedRecommendation.user_id == user_id))


def count_dismissed(session: Session, user_id: int) -> int:
    return session.execute(
        select(func.count()).select_from(DismissedRecommendation).where(DismissedRecommendation.user_id == user_id)
    ).scalar_one()


def list_dismissed(session: Session, user_id: int) -> List[Dict[str, Any]]:
    """A user's dismissed artists, last dismissed first."""
    rows = session.execute(
        select(DismissedRecommendation)
        .where(DismissedRecommendation.user_id == user_id)
        .order_by(DismissedRecommendation.dismissed_at.desc())
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


def dismiss(session: Session, user_id: int, artist_id: str) -> bool:
    """
    Mark an artist "not interested" for a user. Idempotent. False when the
    artist is unknown here (in no similar list, not in the library). No commit.
    """
    if session.get(DismissedRecommendation, (user_id, artist_id)):
        return True
    rel = session.execute(
        select(RelatedArtist).where(RelatedArtist.related_id == artist_id).limit(1)
    ).scalar_one_or_none()
    artist = session.get(Artist, artist_id) if rel is None else None
    if rel is None and artist is None:
        return False
    session.add(DismissedRecommendation(
        user_id=user_id,
        artist_id=artist_id,
        name=rel.name if rel else artist.name,
        thumbnail=rel.thumbnail if rel else None,
    ))
    return True


def restore(session: Session, user_id: int, artist_id: str) -> bool:
    """Undo a user's dismissal. False when it wasn't dismissed. No commit."""
    row = session.get(DismissedRecommendation, (user_id, artist_id))
    if row is None:
        return False
    session.delete(row)
    return True
