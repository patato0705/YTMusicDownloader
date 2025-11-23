// src/hooks/useAsync.ts
import { useState, useEffect, useCallback } from 'react';

/**
 * State returned by useAsync hook
 */
interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/**
 * Return type of useAsync hook
 */
interface AsyncReturn<T> extends AsyncState<T> {
  execute: () => Promise<void>;
  reset: () => void;
}

/**
 * Custom hook for handling async operations with loading and error states
 * 
 * @param asyncFunction - The async function to execute
 * @param immediate - Whether to execute immediately on mount (default: true)
 * @returns Object containing data, loading, error states and control functions
 * 
 * @example
 * const { data, loading, error, execute } = useAsync(
 *   () => fetchArtist(artistId),
 *   true
 * );
 * 
 * // Manual execution
 * const handleRefresh = () => execute();
 */
export function useAsync<T>(
  asyncFunction: () => Promise<T>,
  immediate: boolean = true
): AsyncReturn<T> {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: immediate,
    error: null,
  });

  // Execute the async function
  const execute = useCallback(async () => {
    setState({ data: null, loading: true, error: null });

    try {
      const response = await asyncFunction();
      setState({ data: response, loading: false, error: null });
    } catch (err: any) {
      setState({
        data: null,
        loading: false,
        error: err.message || 'An error occurred',
      });
    }
  }, [asyncFunction]);

  // Reset to initial state
  const reset = useCallback(() => {
    setState({ data: null, loading: false, error: null });
  }, []);

  // Execute on mount if immediate is true
  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, [execute, immediate]);

  return {
    ...state,
    execute,
    reset,
  };
}