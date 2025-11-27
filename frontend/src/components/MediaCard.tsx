// src/components/MediaCard.tsx
import React, { useState } from 'react';

interface MediaCardProps {
  id: string;
  title: string;
  subtitle?: string;
  thumbnail?: string;
  type?: 'artist' | 'album' | 'track';
  year?: string;
  onClick?: () => void;
  className?: string;
}

const MediaCard: React.FC<MediaCardProps> = ({
  id,
  title,
  subtitle,
  thumbnail,
  type = 'album',
  year,
  onClick,
  className = '',
}) => {
  const [imageError, setImageError] = useState(false);

  // The thumbnail prop is already processed by the parent component
  // Just use it directly with a fallback
  const displayUrl = thumbnail || '/assets/placeholder-music.png';

  // Different styling for artists (circular) vs albums/tracks (square)
  const imageStyle = type === 'artist' ? 'rounded-full' : 'rounded-md';

  return (
    <div
      onClick={onClick}
      className={`group cursor-pointer flex-shrink-0 ${className}`}
      style={{ width: '180px' }}
    >
      {/* Image container */}
      <div className="relative mb-3 aspect-square">
        <img
          src={imageError ? '/assets/placeholder-music.png' : displayUrl}
          alt={title}
          className={`w-full h-full object-cover ${imageStyle} bg-secondary transition-opacity group-hover:opacity-75`}
          onError={() => {
            if (!imageError) {
              setImageError(true);
            }
          }}
        />
      </div>

      {/* Text content */}
      <div className="space-y-1">
        <h3 className="font-semibold text-sm text-foreground truncate group-hover:text-primary transition-colors">
          {title}
        </h3>
        
        {subtitle && (
          <p className="text-xs text-muted-foreground truncate">
            {subtitle}
          </p>
        )}
        
        {year && (
          <p className="text-xs text-muted-foreground">
            {year}
          </p>
        )}
        
        {/* Type badge (optional) */}
        {type && (
          <span className="inline-block px-2 py-0.5 text-xs rounded bg-secondary text-secondary-foreground capitalize">
            {type}
          </span>
        )}
      </div>
    </div>
  );
};

export default MediaCard;