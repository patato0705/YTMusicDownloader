import React, { useState, KeyboardEvent, useEffect, useRef } from "react";

interface MediaCardProps {
  id: string;
  title: string;
  subtitle?: string;
  thumbnail?: string | null;
  type?: "artist" | "album" | "track";
  onClick?: () => void;
  className?: string;
  size?: "sm" | "md" | "lg";
  showType?: boolean;
}

export default function MediaCard({
  id,
  title,
  subtitle,
  thumbnail,
  type = "album",
  onClick,
  className = "",
  size = "md",
  showType = false,
}: MediaCardProps) {
  const [imgError, setImgError] = useState(false);
  const [shouldLoad, setShouldLoad] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Proxy external URLs through backend cache
  const displayUrl = (() => {
    if (!thumbnail || imgError) return "/assets/placeholder-music.png";
    
    // If it's a Googleusercontent URL, proxy it through our backend
    if (thumbnail.includes("googleusercontent.com") || thumbnail.includes("ytimg.com")) {
      return `/api/media/thumbnail?url=${encodeURIComponent(thumbnail)}`;
    }
    
    return thumbnail;
  })();

  const cardHeight = size === "sm" ? "h-32" : size === "lg" ? "h-56" : "h-40";
  const imgClass = `w-full h-full object-cover transition-transform duration-200 ease-in-out ${
    imgError ? "opacity-40" : "opacity-100"
  }`;

  const ariaLabel = title + (subtitle ? ` — ${subtitle}` : "");

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!onClick) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick();
    }
  };

  // Intersection Observer for lazy loading
  useEffect(() => {
    if (!containerRef.current || !thumbnail) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const delay = Math.random() * 200;
            setTimeout(() => setShouldLoad(true), delay);
            observer.unobserve(entry.target);
          }
        });
      },
      {
        rootMargin: "50px",
      }
    );

    observer.observe(containerRef.current);

    return () => observer.disconnect();
  }, [thumbnail]);

  return (
    <div
      ref={containerRef}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={handleKeyDown}
      onClick={onClick}
      className={`w-40 flex-shrink-0 bg-white rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow cursor-pointer ${className}`}
      aria-label={ariaLabel}
      title={ariaLabel}
    >
      <div
        className={`w-full ${cardHeight} bg-gray-100 flex items-center justify-center overflow-hidden relative`}
      >
        {thumbnail && shouldLoad ? (
          <img
            ref={imgRef}
            src={displayUrl}
            alt={title}
            loading="lazy"
            className={imgClass}
            onError={() => setImgError(true)}
          />
        ) : thumbnail ? (
          <div className="w-full h-full bg-gray-200 animate-pulse" />
        ) : (
          <div className="text-sm text-gray-400 px-3 text-center">
            {title.length > 20 ? `${title.slice(0, 20)}…` : title}
          </div>
        )}

        {showType && type && (
          <div className="absolute left-2 top-2 bg-black/60 text-white text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide">
            {type === "track" ? "song" : type}
          </div>
        )}
      </div>

      <div className="p-3">
        <div className="text-sm font-medium text-gray-900 truncate" title={title}>
          {title}
        </div>
        {subtitle && (
          <div className="text-xs text-gray-500 truncate mt-1" title={subtitle}>
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );
}