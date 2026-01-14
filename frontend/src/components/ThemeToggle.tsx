'use client';

import { useTheme } from '@/contexts/ThemeContext';
import { Sun, Moon } from 'lucide-react';

export default function ThemeToggle() {
  const { theme, toggleTheme, isLoading } = useTheme();

  if (isLoading) {
    return (
      <div className="flex items-center gap-3 p-4 bg-muted rounded-lg animate-pulse">
        <div className="h-6 w-6 bg-muted-foreground/20 rounded"></div>
        <div className="h-4 flex-1 bg-muted-foreground/20 rounded"></div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between p-4 bg-card border border-border rounded-lg">
      <div className="flex items-center gap-3">
        <div className="text-muted-foreground">
          {theme === 'dark' ? <Moon className="h-6 w-6" /> : <Sun className="h-6 w-6" />}
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">
            Theme Preference
          </div>
          <div className="text-xs text-muted-foreground">
            Current: {theme === 'dark' ? 'Dark Mode' : 'Light Mode'}
          </div>
        </div>
      </div>

      <button
        onClick={toggleTheme}
        className="relative inline-flex h-8 w-14 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 bg-muted"
        role="switch"
        aria-checked={theme === 'dark'}
        aria-label="Toggle theme"
      >
        <span
          className={`inline-block h-6 w-6 transform rounded-full bg-foreground transition-transform ${
            theme === 'dark' ? 'translate-x-7' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  );
}
