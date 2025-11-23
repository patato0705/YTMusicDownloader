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
        
        {/* Hover overlay with play/info icon */}
        <div className={`absolute inset-0 ${imageStyle} bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center`}>
          <svg
            className="w-12 h-12 text-white"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            {type === 'track' ? (
              // Play icon for tracks
              <path d="M8 5v14l11-7z" />
            ) : (
              // Info/expand icon for artists/albums
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
            )}
          </svg>
        </div>
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