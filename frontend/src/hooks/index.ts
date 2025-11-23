// src/hooks/index.ts

/**
 * Central export file for all custom hooks
 * Import hooks like: import { useDebounce, useAsync } from '@/hooks';
 */

export { useDebounce } from './useDebounce';
export { useAsync } from './useAsync';
export { useLocalStorage } from './useLocalStorage';
export { useToggle } from './useToggle';
export {
  useMediaQuery,
  useIsMobile,
  useIsTablet,
  useIsDesktop,
  useIsLargeDesktop,
  usePrefersDarkMode,
} from './useMediaQuery';