# FastAPI Backend Setup Guide

## Step 1: Install Dependencies on Your DigitalOcean Server

SSH into your DigitalOcean server and navigate to the project directory, then run:

```bash
cd /path/to/kingdomautofinance-accounting-system/backend
pip install -r requirements.txt
```

## Step 2: Run Database Migrations

You need to create the new tables in your Supabase database. You have two options:

### Option A: Via Supabase Dashboard (Recommended for first time)

1. Go to https://supabase.com/dashboard
2. Select your project (puwcyhbjchkfvvaccacg)
3. Click "SQL Editor" in the left sidebar
4. Click "New Query"
5. Copy the contents of `backend/migrations/001_initial_tables.sql`
6. Paste into the SQL editor
7. Click "Run" button
8. Verify the tables were created successfully

### Option B: Via Python Script (if you prefer automation)

```bash
cd /path/to/kingdomautofinance-accounting-system/backend
python -c "
import os
from supabase import create_client

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
supabase = create_client(url, key)

with open('migrations/001_initial_tables.sql', 'r') as f:
    sql = f.read()

# Execute migration
result = supabase.rpc('exec_sql', {'sql': sql}).execute()
print('Migration completed!')
"
```

## Step 3: Set Environment Variables

Make sure these environment variables are set on your server:

```bash
export SUPABASE_URL="https://puwcyhbjchkfvvaccacg.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key-here"
export GOOGLE_CREDENTIALS_JSON="your-google-credentials-json"
export SOURCE_PAYMENTS_SHEET_ID="14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8"
export AMORTIZATION_SCHEDULES_FOLDER_ID="1u5nAuQVIRosLsZgPPuPLmRriGRyQf60s"
```

Or create a `.env` file in the `backend` directory:

```bash
cat > /path/to/kingdomautofinance-accounting-system/backend/.env << 'EOF'
SUPABASE_URL=https://puwcyhbjchkfvvaccacg.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
GOOGLE_CREDENTIALS_JSON=your-google-credentials-json
SOURCE_PAYMENTS_SHEET_ID=14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8
AMORTIZATION_SCHEDULES_FOLDER_ID=1u5nAuQVIRosLsZgPPuPLmRriGRyQf60s
EOF
```

## Step 4: Test the FastAPI Server Locally

Run the FastAPI server:

```bash
cd /path/to/kingdomautofinance-accounting-system/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using StatReload
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Visit http://your-server-ip:8000/docs in your browser to see the API documentation.

## Step 5: Run FastAPI as a Background Service

Once everything works, set up FastAPI to run automatically using systemd:

```bash
sudo nano /etc/systemd/system/kaf-api.service
```

Add this content (replace paths with your actual paths):

```ini
[Unit]
Description=Kingdom Auto Finance FastAPI Backend
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/kingdomautofinance-accounting-system/backend
Environment="SUPABASE_URL=https://puwcyhbjchkfvvaccacg.supabase.co"
Environment="SUPABASE_SERVICE_ROLE_KEY=your-key-here"
ExecStart=/usr/local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable kaf-api
sudo systemctl start kaf-api
sudo systemctl status kaf-api
```

## Verification

1. Check API health: `curl http://localhost:8000/health`
2. Check API docs: http://your-server-ip:8000/docs
3. Check logs: `sudo journalctl -u kaf-api -f`

## Next Steps

Once the API is running, we'll:
1. Migrate the business logic from `src/` to FastAPI endpoints
2. Update the Streamlit UI to call the API instead of subprocess
3. Test that everything works the same as before
