// src/hooks/useMediaQuery.ts
import { useState, useEffect } from 'react';

/**
 * Custom hook for responsive media queries
 * 
 * @param query - The media query string (e.g., '(min-width: 768px)')
 * @returns Boolean indicating if the media query matches
 * 
 * @example
 * const isMobile = useMediaQuery('(max-width: 768px)');
 * const isDesktop = useMediaQuery('(min-width: 1024px)');
 * const prefersDark = useMediaQuery('(prefers-color-scheme: dark)');
 * 
 * return (
 *   <div>
 *     {isMobile ? <MobileNav /> : <DesktopNav />}
 *   </div>
 * );
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.matchMedia(query).matches;
    }
    return false;
  });

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const mediaQuery = window.matchMedia(query);
    
    // Update state if query result changes
    const handleChange = (event: MediaQueryListEvent) => {
      setMatches(event.matches);
    };

    // Set initial value
    setMatches(mediaQuery.matches);

    // Listen for changes
    mediaQuery.addEventListener('change', handleChange);

    // Clean up
    return () => {
      mediaQuery.removeEventListener('change', handleChange);
    };
  }, [query]);

  return matches;
}

/**
 * Predefined breakpoint hooks for common screen sizes
 */
export const useIsMobile = () => useMediaQuery('(max-width: 767px)');
export const useIsTablet = () => useMediaQuery('(min-width: 768px) and (max-width: 1023px)');
export const useIsDesktop = () => useMediaQuery('(min-width: 1024px)');
export const useIsLargeDesktop = () => useMediaQuery('(min-width: 1280px)');
export const usePrefersDarkMode = () => useMediaQuery('(prefers-color-scheme: dark)');