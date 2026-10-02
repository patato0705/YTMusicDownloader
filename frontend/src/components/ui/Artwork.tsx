// src/components/ui/Artwork.tsx
import React, { useState } from 'react';

interface ArtworkProps {
  /** Resolved image URL (see getImageUrl) - empty means there's no artwork yet */
  src?: string | null;
  /** Name of the artist / album - its initials are drawn on the fallback */
  name?: string | null;
  /** Stable key (usually the id) picking the fallback colours; defaults to the name */
  seed?: string | null;
  /** Applied to the wrapper: size, shape, ring, shadow, hover effects... */
  className?: string;
  loading?: 'lazy' | 'eager';
}

/** FNV-1a: small, fast, and spreads similar strings far apart */
function hashString(value: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/** Up to two letters from the first words, ignoring "(Deluxe)"-style suffixes and leading symbols */
export function getInitials(name?: string | null): string {
  const words = (name || '')
    .replace(/[([{].*?[)\]}]/g, ' ')
    .split(/\s+/)
    .map((word) => word.replace(/^[^\p{L}\p{N}]+/u, ''))
    .filter(Boolean);

  return words
    .slice(0, 2)
    .map((word) => Array.from(word)[0])
    .join('')
    .toLocaleUpperCase();
}

/** Same seed, same gradient - so an item keeps its colours across pages and reloads */
function gradientFor(seed: string): string {
  const hash = hashString(seed);
  const hue = hash % 360;
  const hue2 = (hue + 30 + ((hash >>> 9) % 60)) % 360;
  const angle = 100 + ((hash >>> 17) % 120);
  return [
    'radial-gradient(circle at 30% 20%, rgba(255,255,255,0.25), transparent 60%)',
    `linear-gradient(${angle}deg, hsl(${hue} 70% 55%), hsl(${hue2} 65% 38%))`,
  ].join(', ');
}

/**
 * Cover / artist picture with a generated fallback: a gradient picked from the
 * item's id, with its initials on top. The fallback also shows while the image
 * loads, and whenever it fails.
 */
export const Artwork: React.FC<ArtworkProps> = ({
  src,
  name,
  seed,
  className = '',
  loading = 'lazy',
}) => {
  // Remember which URL failed rather than a flag: an artist starts with no
  // cover and gets one once its sync job lands, and that new URL must be tried
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const imageSrc = src && src !== failedSrc ? src : null;
  const initials = getInitials(name);

  return (
    <div className={`relative overflow-hidden ${className}`}>
      <div
        className="absolute inset-0"
        style={{ backgroundImage: gradientFor(seed || name || '') }}
        aria-hidden="true"
      >
        {/* SVG text scales with the artwork, from a list thumbnail to a page header */}
        <svg viewBox="0 0 100 100" className="w-full h-full select-none">
          <text
            x="50"
            y="50"
            dy="0.35em"
            textAnchor="middle"
            fill="white"
            fillOpacity="0.92"
            fontSize={initials.length > 1 ? 38 : 46}
            fontWeight="700"
            letterSpacing="1"
          >
            {initials || '♪'}
          </text>
        </svg>
      </div>

      {/* Decorative: the name is always written next to it, and an alt text
          would be drawn over the fallback while the image loads or fails */}
      {imageSrc && (
        <img
          src={imageSrc}
          alt=""
          loading={loading}
          decoding="async"
          className="absolute inset-0 w-full h-full object-cover"
          onError={() => setFailedSrc(imageSrc)}
        />
      )}
    </div>
  );
};

export default Artwork;
