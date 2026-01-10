'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { settingsAPI } from '@/lib/api';

type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  isLoading: boolean;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('light');
  const [isLoading, setIsLoading] = useState(true);

  // Load theme from backend on mount
  useEffect(() => {
    const loadTheme = async () => {
      try {
        const setting = await settingsAPI.get('THEME_PREFERENCE');
        const savedTheme = (setting.value === 'dark' ? 'dark' : 'light') as Theme;
        setThemeState(savedTheme);
        applyThemeToDOM(savedTheme);
      } catch (error) {
        console.error('Failed to load theme preference:', error);
        // Default to light mode on error
        applyThemeToDOM('light');
      } finally {
        setIsLoading(false);
      }
    };

    loadTheme();
  }, []);

  // Apply theme class to html element
  const applyThemeToDOM = (newTheme: Theme) => {
    const root = document.documentElement;
    if (newTheme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  };

  // Set theme and persist to backend
  const setTheme = async (newTheme: Theme) => {
    setThemeState(newTheme);
    applyThemeToDOM(newTheme);

    // Persist to backend
    try {
      await settingsAPI.update('THEME_PREFERENCE', newTheme);
      await settingsAPI.clearCache();
    } catch (error) {
      console.error('Failed to save theme preference:', error);
      // Theme still applied locally even if save fails
    }
  };

  const toggleTheme = () => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme, isLoading }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
