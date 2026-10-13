// src/contexts/ThemeContext.tsx
import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';

type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const STORAGE_KEY = 'theme';
const systemQuery = () => window.matchMedia('(prefers-color-scheme: dark)');

/** The theme picked with the toggle; none means following the system */
function storedTheme(): Theme | null {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === 'light' || stored === 'dark' ? stored : null;
}

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? (systemQuery().matches ? 'dark' : 'light'));

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    // Tint the mobile browser chrome to match (values mirror --color-background)
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', theme === 'dark' ? '#09090b' : '#f8fafc');
  }, [theme]);

  // Follow the system setting until a theme is picked with the toggle
  useEffect(() => {
    const query = systemQuery();
    const handleChange = (e: MediaQueryListEvent) => {
      if (!storedTheme()) setTheme(e.matches ? 'dark' : 'light');
    };
    query.addEventListener('change', handleChange);
    return () => query.removeEventListener('change', handleChange);
  }, []);

  const value = useMemo(() => ({
    theme,
    toggleTheme: () => {
      const next = theme === 'light' ? 'dark' : 'light';
      localStorage.setItem(STORAGE_KEY, next);
      setTheme(next);
    },
  }), [theme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
};
