-- Migration: Create system_settings table for dynamic configuration
-- Purpose: Allow users to configure Google Sheets and Drive URLs through the UI

CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    category VARCHAR(50) DEFAULT 'general',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for filtering by category
CREATE INDEX IF NOT EXISTS idx_system_settings_category ON system_settings(category);

-- Create function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_system_settings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for automatic timestamp update
DROP TRIGGER IF EXISTS trigger_update_system_settings_updated_at ON system_settings;
CREATE TRIGGER trigger_update_system_settings_updated_at
    BEFORE UPDATE ON system_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_system_settings_updated_at();

-- Seed with current hardcoded values from src/config.py
-- This ensures zero-downtime migration - existing values continue to work
INSERT INTO system_settings (key, value, description, category) VALUES
    ('SOURCE_PAYMENTS_SHEET_ID', '14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8', 'Google Sheet ID for source payments data imported into the system', 'google_integration'),
    ('AMORTIZATION_SCHEDULES_FOLDER_ID', '1u5nAuQVIRosLsZgPPuPLmRriGRyQf60s', 'Google Drive folder ID containing individual loan amortization schedule spreadsheets', 'google_integration')
ON CONFLICT (key) DO NOTHING;

-- Verify data was inserted
SELECT * FROM system_settings WHERE category = 'google_integration';
