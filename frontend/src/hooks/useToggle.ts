// src/hooks/useToggle.ts
import { useState, useCallback } from 'react';

/**
 * Custom hook for boolean toggle state
 * 
 * @param initialValue - Initial boolean value (default: false)
 * @returns [value, toggle, setTrue, setFalse] tuple
 * 
 * @example
 * const [isOpen, toggle, open, close] = useToggle(false);
 * 
 * <button onClick={toggle}>Toggle</button>
 * <button onClick={open}>Open</button>
 * <button onClick={close}>Close</button>
 */
export function useToggle(
  initialValue: boolean = false
): [boolean, () => void, () => void, () => void] {
  const [value, setValue] = useState(initialValue);

  const toggle = useCallback(() => {
    setValue((v) => !v);
  }, []);

  const setTrue = useCallback(() => {
    setValue(true);
  }, []);

  const setFalse = useCallback(() => {
    setValue(false);
  }, []);

  return [value, toggle, setTrue, setFalse];
}