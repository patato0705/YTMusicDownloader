// src/components/ui/GenreChips.tsx
import React from 'react';

interface GenreChipsProps {
  genres?: string[] | null;
  className?: string;
}

/**
 * An album's or artist's genres (looked up on MusicBrainz / Deezer, see
 * backend/services/genres.py) as small pills. Renders nothing without any.
 */
export const GenreChips: React.FC<GenreChipsProps> = ({ genres, className = '' }) => {
  if (!genres || genres.length === 0) return null;
  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {genres.map((genre) => (
        <span
          key={genre}
          className="px-3 py-1 rounded-full glass text-sm text-muted-foreground"
        >
          {genre}
        </span>
      ))}
    </div>
  );
};
