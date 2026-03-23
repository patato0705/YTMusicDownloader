// src/components/charts/ChartArtistGrid.tsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { getImageUrl } from '../../api/media';
import type { ChartArtist } from '../../api/charts';

interface ChartArtistGridProps {
  artists: ChartArtist[];
  maxHeight?: string;
}

export const ChartArtistGrid: React.FC<ChartArtistGridProps> = ({ 
  artists, 
  maxHeight = '200px' 
}) => {
  const navigate = useNavigate();

  const getTrendIcon = (trend: 'up' | 'down' | 'neutral') => {
    switch (trend) {
      case 'up':
        return '↑';
      case 'down':
        return '↓';
      default:
        return '–';
    }
  };

  const getTrendColor = (trend: 'up' | 'down' | 'neutral') => {
    switch (trend) {
      case 'up':
        return 'bg-green-500';
      case 'down':
        return 'bg-red-500';
      default:
        return 'bg-slate-400';
    }
  };

  return (
    <div 
      className="overflow-y-auto pr-2 custom-scrollbar" 
      style={{ maxHeight }}
    >
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {artists.map((artist) => {
          const thumbnail = artist.thumbnails?.[1]?.url || artist.thumbnails?.[0]?.url;
          const isfollowed = artist.followed

          return (
            <button
              key={artist.id}
              onClick={() => navigate(`/artists/${encodeURIComponent(artist.id)}`)}
              className="relative group flex flex-col items-center gap-2 p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-white/5 transition-all"
            >
              {/* Artist Image Circle */}
              <div className="relative w-16 h-16">
                {/* Rank Badge - Top Left */}
                <div className="absolute -top-1 -left-1 z-10 w-6 h-6 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 dark:from-red-600 dark:to-red-700 flex items-center justify-center shadow-lg border-2 border-white dark:border-zinc-900">
                  <span className="text-[10px] font-bold text-white">{artist.rank}</span>
                </div>

                {/* Artist Image */}
                <div className="w-full h-full rounded-full overflow-hidden bg-slate-200 dark:bg-white/10 border-2 border-slate-300 dark:border-white/20 group-hover:border-blue-500 dark:group-hover:border-red-500 transition-all">
                  {thumbnail ? (
                    <img
                      src={getImageUrl(thumbnail)}
                      alt={artist.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-2xl">
                      👤
                    </div>
                  )}
                </div>

                {/* Trend Indicator - Bottom Right */}
                <div 
                  className={`absolute -bottom-1 -right-1 z-10 w-5 h-5 rounded-full ${getTrendColor(artist.trend)} flex items-center justify-center shadow-lg border-2 border-white dark:border-zinc-900`}
                >
                  <span className="text-[10px] font-bold text-white">
                    {getTrendIcon(artist.trend)}
                  </span>
                </div>
              </div>

              {/* Artist Name */}
              <span className="text-xs font-medium text-center text-foreground line-clamp-1 w-full px-1">
                {artist.name}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};