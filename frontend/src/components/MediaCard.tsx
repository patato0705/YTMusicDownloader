// src/components/MediaCard.tsx
import React, { useState } from 'react';

export type MediaStatus = 'downloaded' | 'in_library' | undefined;

interface MediaCardProps {
  id: string;
  title: string;
  subtitle?: string;
  thumbnail?: string;
  type?: 'artist' | 'album' | 'track';
  year?: string;
  mediaStatus?: MediaStatus;
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
  mediaStatus,
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

        {/* Status badge */}
        {mediaStatus === 'downloaded' && (
          <div className="absolute bottom-2 left-2 w-6 h-6 rounded-full bg-green-500/90 backdrop-blur-sm flex items-center justify-center shadow-md" title="On disk">
            <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        )}
        {mediaStatus === 'in_library' && (
          <div className="absolute bottom-2 left-2 w-6 h-6 rounded-full bg-blue-500/90 dark:bg-red-600/90 backdrop-blur-sm flex items-center justify-center shadow-md" title="In library">
            <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
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