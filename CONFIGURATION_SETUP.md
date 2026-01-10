# Configuration Management Setup Guide

## Overview
This guide walks you through setting up the new configuration management system that allows you to configure Google Sheets and Drive URLs through the maintenance page UI.

## Implementation Complete ✅

All code has been implemented. You just need to run the database migration and test the system.

## Setup Steps

### 1. Run Database Migration

Connect to your Supabase database and run the migration file:

```bash
# Option A: Using psql command line
psql "postgresql://postgres:[YOUR-PASSWORD]@[YOUR-HOST]:[PORT]/postgres" \
  -f backend/migrations/002_system_settings.sql

# Option B: Using Supabase SQL Editor
# Copy the contents of backend/migrations/002_system_settings.sql
# Paste into Supabase Dashboard > SQL Editor > New Query
# Click "Run"
```

The migration will:
- Create `system_settings` table
- Add automatic timestamp triggers
- Seed with your current hardcoded values (zero-downtime migration)

### 2. Verify Migration

Check that the settings were inserted:

```sql
SELECT * FROM system_settings WHERE category = 'google_integration';
```

You should see:
- `SOURCE_PAYMENTS_SHEET_ID` = `14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8`
- `AMORTIZATION_SCHEDULES_FOLDER_ID` = `1u5nAuQVIRosLsZgPPuPLmRriGRyQf60s`

### 3. Restart Backend (Already Done)

The backend should now be running successfully:

```bash
cd backend
python -m uvicorn app.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### 4. Test the API Endpoints

```bash
# Get current settings
curl http://localhost:8000/api/v1/settings

# Get specific setting
curl http://localhost:8000/api/v1/settings/SOURCE_PAYMENTS_SHEET_ID

# Update a setting (with validation)
curl -X PUT http://localhost:8000/api/v1/settings/SOURCE_PAYMENTS_SHEET_ID \
  -H "Content-Type: application/json" \
  -d '{"value": "https://docs.google.com/spreadsheets/d/YOUR_NEW_SHEET_ID/edit", "type": "sheet"}'

# Clear cache
curl -X POST http://localhost:8000/api/v1/settings/cache/clear
```

### 5. Test the Frontend

1. Open your browser and navigate to the maintenance page
2. You should see three accordion sections:
   - 📥 Import Amortization Schedules (open by default)
   - 📊 Google Payments Sheet Configuration
   - 📁 Google Drive Folder Configuration

3. Expand the configuration sections and verify:
   - Current values are loaded from the database
   - Input fields are editable
   - "Save Changes" button is disabled until you make changes

### 6. Test Configuration Updates

**Test with Full URL:**
1. Expand "Google Payments Sheet Configuration"
2. Paste a full Google Sheets URL (e.g., `https://docs.google.com/spreadsheets/d/ABC123/edit`)
3. Click "Save Changes"
4. Should see "Settings updated successfully!" message
5. Behind the scenes, it:
   - Extracts the Sheet ID (`ABC123`)
   - Validates access to the sheet via Google API
   - Saves to database
   - Clears cache

**Test with Direct ID:**
1. Try entering just the ID (e.g., `ABC123XYZ`)
2. Should work the same way

**Test Validation:**
1. Try an invalid URL → Should show error
2. Try a Sheet ID you don't have access to → Should show "Cannot access Google Sheet"

### 7. Verify Import Uses New Settings

After updating a setting:

1. Go back to "Import Amortization Schedules" section
2. Click "Import Schedules from Google Drive"
3. The import should use the new Folder ID from your settings
4. Similarly, payment fetches will use the new Sheet ID

## What Was Implemented

### Backend Files Created
- `backend/migrations/002_system_settings.sql` - Database schema
- `backend/app/services/settings_service.py` - Settings manager with caching
- `backend/app/services/google_validator.py` - Google API access validation
- `backend/app/core/settings_manager.py` - Singleton instance
- `backend/app/api/settings.py` - REST API endpoints

### Backend Files Modified
- `src/config.py` - Now reads from settings manager → env vars → defaults
- `backend/app/main.py` - Added settings router

### Frontend Files Created
- `frontend/src/components/Accordion.tsx` - Custom accordion component
- `frontend/src/components/SettingsForm.tsx` - Settings form with validation

### Frontend Files Modified
- `frontend/src/lib/api.ts` - Added settingsAPI
- `frontend/src/app/maintenance/page.tsx` - Restructured with accordion UI

## Features

### URL Flexibility
- **Full URLs**: `https://docs.google.com/spreadsheets/d/ABC123/edit`
- **Direct IDs**: `ABC123`
- Automatically extracts and validates IDs

### Google API Validation
- Tests access before saving
- Clear error messages:
  - "Google Sheet not found"
  - "Permission denied accessing Google Sheet"
  - "Invalid Google Sheet URL or ID format"

### Caching
- 5-minute in-memory cache on backend
- Automatic cache clear after updates
- Manual cache clear endpoint available

### Fallback Chain
1. **Database** (primary) - Settings from UI
2. **Environment Variables** - Override if set
3. **Hardcoded Defaults** - Final fallback

## Troubleshooting

### Backend won't start
- Check that migration was run successfully
- Verify Supabase credentials are set: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`

### Settings not loading
- Check browser console for API errors
- Verify backend is running on port 8000
- Check that migration created the table

### Validation errors
- Ensure service account has access to the Sheet/Folder
- Check that `GOOGLE_SERVICE_ACCOUNT_JSON` environment variable is set
- Try the direct ID instead of full URL

### Changes not taking effect
- Settings are cached for 5 minutes
- Wait or manually clear cache via API: `POST /api/v1/settings/cache/clear`
- Alternatively, restart the backend

## Rollback Plan

If you need to rollback:

1. **Use environment variables** to override database settings:
   ```bash
   export SOURCE_PAYMENTS_SHEET_ID="your_original_id"
   export AMORTIZATION_SCHEDULES_FOLDER_ID="your_original_folder_id"
   ```

2. **Drop the settings table** (if needed):
   ```sql
   DROP TABLE IF EXISTS system_settings CASCADE;
   ```

3. The system will automatically fall back to the original hardcoded values in `src/config.py`

## Next Steps

After verifying everything works:

1. **Document your Sheet/Folder IDs** for backup
2. **Train users** on how to update settings via the UI
3. **Monitor logs** for any validation errors
4. **Consider adding more settings** in the future (same pattern)

## Support

If you encounter issues:
1. Check backend logs: `docker logs [container-id]`
2. Check browser console for frontend errors
3. Verify database migration ran successfully
4. Test API endpoints directly with curl
