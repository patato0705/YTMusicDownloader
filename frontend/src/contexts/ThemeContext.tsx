// src/contexts/ThemeContext.tsx
import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';
import ACCENTS from '../config/accents.json';
import { readStorage, writeStorage } from '../utils/storage';

type Theme = 'light' | 'dark';

/** The accent colours on offer (config/accents.json), the first being the default */
export { ACCENTS };

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  accent: string;
  setAccent: (accent: string) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

// Both also read by the pre-paint script in index.html
const STORAGE_KEY = 'theme';
const ACCENT_STORAGE_KEY = 'accent';
const systemQuery = () => window.matchMedia('(prefers-color-scheme: dark)');

/** The theme picked in the appearance menu; none means following the system */
function storedTheme(): Theme | null {
  const stored = readStorage(STORAGE_KEY);
  return stored === 'light' || stored === 'dark' ? stored : null;
}

function storedAccent(): string {
  const stored = readStorage(ACCENT_STORAGE_KEY);
  return stored && ACCENTS.includes(stored) ? stored : ACCENTS[0];
}

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(() => storedTheme() ?? (systemQuery().matches ? 'dark' : 'light'));
  const [accent, setAccentState] = useState(storedAccent);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    // Tint the mobile browser chrome to match (values mirror --color-background)
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', theme === 'dark' ? '#09090b' : '#f8fafc');
  }, [theme]);

  // The --accent-* variables under this attribute (tailwind.config.cjs)
  useEffect(() => {
    document.documentElement.dataset.accent = accent;
  }, [accent]);

  // Follow the system setting until a theme is picked in the appearance menu
  useEffect(() => {
    const query = systemQuery();
    const handleChange = (e: MediaQueryListEvent) => {
      if (!storedTheme()) setThemeState(e.matches ? 'dark' : 'light');
    };
    query.addEventListener('change', handleChange);
    return () => query.removeEventListener('change', handleChange);
  }, []);

  const value = useMemo(() => ({
    theme,
    setTheme: (next: Theme) => {
      writeStorage(STORAGE_KEY, next);
      setThemeState(next);
    },
    accent,
    setAccent: (next: string) => {
      writeStorage(ACCENT_STORAGE_KEY, next);
      setAccentState(next);
    },
  }), [theme, accent]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
};
