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

  const displayUrl = thumbnail || '/assets/placeholder-music.png';
  const imageStyle = type === 'artist' ? 'rounded-full' : 'rounded-xl';

  return (
    <div
      onClick={onClick}
      className={`group cursor-pointer transition-all duration-300 hover-lift ${className}`}
    >
      {/* Image container with glassmorphic overlay on hover */}
      <div className={`relative mb-3 overflow-hidden ${type === 'artist' ? 'aspect-square' : 'aspect-square'} ${imageStyle}`}>
        <img
          src={imageError ? '/assets/placeholder-music.png' : displayUrl}
          alt={title}
          className={`w-full h-full object-cover ${imageStyle} bg-slate-200 dark:bg-zinc-800 transition-all duration-300 group-hover:scale-105`}
          onError={() => {
            if (!imageError) {
              setImageError(true);
            }
          }}
        />
        
        {/* Gradient overlay on hover */}
        <div className={`absolute inset-0 bg-gradient-to-t from-black/60 via-black/0 to-black/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 ${imageStyle}`} />
        
        {/* Type badge */}
        {type && (
          <div className="absolute top-2 right-2 px-2 py-1 text-xs font-medium rounded-lg glass backdrop-blur-md text-blue-600 dark:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
            {type.charAt(0).toUpperCase() + type.slice(1)}
          </div>
        )}
      </div>

      {/* Text content - centered for artists */}
      <div className={`space-y-1 px-1 ${type === 'artist' ? 'text-center' : ''}`}>
        <h3 className="font-semibold text-sm text-foreground truncate group-hover:text-blue-600 dark:group-hover:text-red-400 transition-colors">
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
      </div>
    </div>
  );
};

export default MediaCard;