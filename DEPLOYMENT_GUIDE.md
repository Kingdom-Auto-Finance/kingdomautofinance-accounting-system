# Deployment Guide: Kingdom Auto Finance v2.0

## Overview

This guide explains how to deploy the new React/Next.js frontend alongside the FastAPI backend on your DigitalOcean server.

## Architecture

```
DigitalOcean Container
├── FastAPI Backend (port 8000)
│   └── Background job workers (Python threading)
└── Next.js Frontend (port 3000)
    └── Connects to FastAPI for all data
```

## Prerequisites

- Your DigitalOcean server/container
- Access to push Docker images
- Environment variables configured

## Deployment Steps

### Option 1: Build Both Services in One Container

Update your main Dockerfile to build and run both services:

```dockerfile
# File: Dockerfile
FROM python:3.11-slim AS python-base

WORKDIR /app

# Install Python dependencies
COPY requirements.txt backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r backend/requirements.txt

# Copy Python code
COPY src/ ./src/
COPY backend/ ./backend/
COPY *.py ./

# Install Node.js
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Build Next.js frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Back to root
WORKDIR /app

# Copy startup script
COPY start-services.sh ./
RUN chmod +x start-services.sh

ENV NEXT_PUBLIC_API_URL=http://localhost:8000

EXPOSE 3000 8000

CMD ["./start-services.sh"]
```

### Option 2: Separate Containers (Recommended)

Deploy FastAPI and Next.js as separate containers:

#### FastAPI Container

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./
COPY requirements.txt ./root-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r root-requirements.txt

COPY src/ ./src/
COPY backend/ ./backend/
COPY *.py ./

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Next.js Container

Use the existing `frontend/Dockerfile` (already created).

### Startup Script for Single Container

```bash
#!/bin/bash
# File: start-services.sh

echo "Starting Kingdom Auto Finance v2.0"
echo "===================================="

# Start FastAPI backend
echo "Starting FastAPI on port 8000..."
cd /app/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!

# Wait for FastAPI to be ready
sleep 3

# Start Next.js frontend
echo "Starting Next.js on port 3000..."
cd /app/frontend/.next/standalone
PORT=3000 node server.js &
NEXTJS_PID=$!

# Wait for both processes
wait $FASTAPI_PID $NEXTJS_PID
```

## Environment Variables

Create `.env` file in your deployment:

```bash
# Backend
SUPABASE_URL=https://puwcyhbjchkfvvaccacg.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-key-here
GOOGLE_CREDENTIALS_JSON=your-credentials-here

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_SECRET=your-random-secret-key
```

## Port Configuration

You need to expose the Next.js port (3000) to the internet:

### Update your DigitalOcean/Kubernetes Service

If using Kubernetes (based on your pod names), update your service:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: kingdomautofinance-accounting-service
spec:
  ports:
    - name: frontend
      port: 80
      targetPort: 3000  # Next.js
    - name: api
      port: 8000
      targetPort: 8000  # FastAPI (optional, for direct API access)
  selector:
    app: kingdomautofinance-accounting
```

## DNS Configuration

Update your DNS to point to the new Next.js frontend:

- `accounting.kingdomautofinance.com` → port 3000 (Next.js)
- `api.kingdomautofinance.com` → port 8000 (FastAPI, optional)

## Build Commands

### On Your Server

```bash
# Navigate to project root
cd /app

# Build and run (if using Docker Compose)
docker-compose up --build -d

# OR if rebuilding existing container
# (Your exact command depends on your setup)
docker build -t kingdom-accounting:v2 .
docker run -p 3000:3000 -p 8000:8000 kingdom-accounting:v2
```

## Testing the Deployment

Once deployed:

1. **Check FastAPI**: `curl http://your-server:8000/health`
2. **Check Next.js**: Visit `http://your-server:3000` in browser
3. **Test Login**: Use password `Kingdom2025!$$`
4. **Test API Connection**: Try fetching a report from the Dashboard

## Troubleshooting

### Next.js Can't Connect to FastAPI

**Problem**: API calls fail with connection errors

**Solution**:
- Make sure `NEXT_PUBLIC_API_URL` points to the correct FastAPI URL
- If both services are in the same container, use `http://localhost:8000`
- If separate containers, use the FastAPI service name or IP

### Images Not Loading

**Problem**: Kingdom Auto Finance logo doesn't appear

**Solution**: Already configured in `next.config.mjs` with remote patterns

### Build Fails

**Problem**: npm install or build fails

**Solution**:
```bash
cd frontend
rm -rf node_modules .next
npm install
npm run build
```

## Rollback Plan

If something goes wrong, you can quickly rollback:

1. **Your Streamlit app is still in the codebase** (`ui.py`)
2. **Change your Dockerfile CMD back to**:
   ```dockerfile
   CMD ["streamlit", "run", "ui.py", "--server.port=8080"]
   ```
3. **Rebuild and redeploy**

## Next Steps After Deployment

1. ✅ Test all features (payments, reports, maintenance)
2. ✅ Verify job progress tracking works
3. ✅ Test CSV downloads
4. ✅ Check mobile responsiveness
5. 🔄 Phase 3: Add enhanced features (multi-user, charts, etc.)

## Support

If you encounter issues:
1. Check logs: `docker logs <container-id>`
2. Verify environment variables are set
3. Test FastAPI directly: `http://your-server:8000/docs`
4. Test Next.js: `http://your-server:3000`

---

**Ready to deploy?** Follow the steps above based on your current setup!
