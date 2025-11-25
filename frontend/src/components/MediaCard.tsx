// src/components/MediaCard.tsx
import React from 'react';

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
  // Proxy external thumbnails through backend cache
  const displayUrl = (() => {
    if (!thumbnail) return '/assets/placeholder-music.png';
    
    // If it's a Googleusercontent or YouTube thumbnail, proxy it
    if (thumbnail.includes('googleusercontent.com') || thumbnail.includes('ytimg.com')) {
      return `/api/media/thumbnail?url=${encodeURIComponent(thumbnail)}`;
    }
    
    return thumbnail;
  })();

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
          src={displayUrl}
          alt={title}
          className={`w-full h-full object-cover ${imageStyle} bg-secondary transition-opacity group-hover:opacity-75`}
          onError={(e) => {
            // Fallback to placeholder on error
            e.currentTarget.src = '/assets/placeholder-music.png';
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