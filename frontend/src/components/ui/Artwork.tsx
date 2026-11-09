// src/components/ui/Artwork.tsx
import React, { useCallback, useState } from 'react';
import { ICON_PATHS } from './icons';

export type ArtworkKind = 'artist' | 'album' | 'track' | 'playlist';

interface ArtworkProps {
  /** Resolved image URL (see getImageUrl) - empty means there's no artwork yet */
  src?: string | null;
  /** What the picture stands for: picks the icon drawn when there's none */
  kind: ArtworkKind;
  /** Applied to the wrapper: size, shape, ring, shadow, hover effects... */
  className?: string;
  loading?: 'lazy' | 'eager';
}

/**
 * Cover / artist picture on a neutral tile. While the image loads, a faint
 * shimmer runs over the tile and the image fades in once it's whole; with no
 * image (or a broken one) the tile shows a muted icon, the way YTM does.
 */
export const Artwork: React.FC<ArtworkProps> = ({
  src,
  kind,
  className = '',
  loading = 'lazy',
}) => {
  // Remember which URL failed / loaded rather than flags: an artist starts with
  // no cover and gets one once its sync job lands, and that new URL must be tried
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const imageSrc = src && src !== failedSrc ? src : null;
  const loaded = imageSrc !== null && imageSrc === loadedSrc;

  // An image already in the cache is complete before React sees it: show it
  // at once instead of fading in every cover on each page visit
  const imageRef = useCallback((img: HTMLImageElement | null) => {
    if (imageSrc && img?.complete && img.naturalWidth > 0) setLoadedSrc(imageSrc);
  }, [imageSrc]);

  return (
    <div className={`relative overflow-hidden bg-slate-200 dark:bg-zinc-800 ${className}`}>
      {imageSrc ? (
        !loaded && (
          <div
            className="absolute inset-0 -translate-x-full animate-artwork-shimmer bg-gradient-to-r from-transparent via-white/50 dark:via-white/[0.06] to-transparent motion-reduce:hidden"
            aria-hidden="true"
          />
        )
      ) : (
        // Sized against the tile so it reads the same from a list thumbnail to a page header
        <svg
          className="absolute inset-0 m-auto w-[30%] h-[30%] text-slate-400 dark:text-zinc-600"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d={kind === 'artist' ? ICON_PATHS.user : ICON_PATHS.music}
          />
        </svg>
      )}

      {/* Decorative: the name is always written next to it, and an alt text
          would be drawn over the tile while the image loads or fails */}
      {imageSrc && (
        <img
          ref={imageRef}
          src={imageSrc}
          alt=""
          loading={loading}
          decoding="async"
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-200 motion-reduce:transition-none ${loaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setLoadedSrc(imageSrc)}
          onError={() => setFailedSrc(imageSrc)}
        />
      )}
    </div>
  );
};
