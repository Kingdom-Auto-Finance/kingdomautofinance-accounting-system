-- Migration: Add theme preference setting
-- Purpose: Store user's dark mode preference

-- Insert theme setting with default light mode
INSERT INTO system_settings (key, value, description, category) VALUES
    ('THEME_PREFERENCE', 'light', 'User interface theme preference (light or dark)', 'ui_preferences')
ON CONFLICT (key) DO NOTHING;

-- Verify
SELECT * FROM system_settings WHERE key = 'THEME_PREFERENCE';
